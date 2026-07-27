"""MaterializationService — export agents/environments to disk, import from disk.

All dedup, checksum, and path-safety logic lives here.  The CLI modules are
thin callers: parse args → call service → print → exit code.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

from agentbox.core.agents import build_config_json_payload, inline_to_composition
from agentbox.core.config import load_settings
from agentbox.core.data.constants import ResourceType
from agentbox.core.data.errors import AgentNotFound
from agentbox.core.data.payload_types import (
    ExportAction,
    ExportedFile,
    ExportReport,
    ImportAction,
    ImportOutcome,
    ImportReport,
)
from agentbox.core.service.agent_formats import AgentFileFormat, dump_agent, parse_agent
from agentbox.core.service.agents import AgentService
from agentbox.core.service.base import Service
from agentbox.core.service.resources import ResourceService
from agentbox.core.service.workspaces import WorkspaceService
from agentbox.core.workspaces import Workspaces


# ── Module-level helpers ──────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Strip trailing whitespace, normalize to LF, strip leading/trailing blank lines."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").splitlines()]
    return "\n".join(lines).strip()


def _checksum(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode()).hexdigest()


def _dest_safe(dest: Path, *, force: bool) -> None:
    """Raise ``ValueError`` if dest is non-empty and force is False."""
    if dest.exists() and any(dest.iterdir()) and not force:
        raise ValueError(
            f"Destination {dest} is not empty — pass --force to overwrite"
        )


def _write_file(dest: Path, name: str, content: str) -> ExportedFile:
    """Write content to dest/name; return an ExportedFile with the action taken."""
    path = dest / name
    action = ExportAction.overwritten if path.exists() else ExportAction.written
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ExportedFile(path=name, action=action)


def _dir_to_zip(src_dir: Path) -> bytes:
    """Pack src_dir into an in-memory ZIP (sorted for determinism)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src_dir))
    return buf.getvalue()


# ── Service ───────────────────────────────────────────────────────────────────


class MaterializationService(Service):
    """Export agents/environments to disk; import agents/skills from disk."""

    def export_agent(
        self,
        agent_id: str,
        fmt: AgentFileFormat,
        dest_dir: Path,
        *,
        force: bool = False,
    ) -> ExportReport:
        """Export one agent to dest_dir in the given format."""
        agent = AgentService().get_agent_def(agent_id)
        if agent is None:
            raise AgentNotFound(agent_id)
        _dest_safe(dest_dir, force=force)
        dest_dir.mkdir(parents=True, exist_ok=True)
        file_pairs = dump_agent(agent, AgentFileFormat(fmt))
        files = [_write_file(dest_dir, name, content) for name, content in file_pairs]
        return ExportReport(dest=str(dest_dir), files=files, agents=[agent_id])

    def export_environment(
        self,
        ws_id: str,
        dest_dir: Path,
        *,
        force: bool = False,
    ) -> ExportReport:
        """Export a workspace environment (env-doc + bindings + subagents) to dest_dir."""
        ws_svc = WorkspaceService()
        ws_svc.require_workspace(ws_id)  # raises WorkspaceNotFound if absent
        _dest_safe(dest_dir, force=force)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Render workspace into dest_dir (non-persistent — no orphan reconcile)
        settings = load_settings()
        facade = Workspaces(self._db.workspace_read, settings)
        facade.build(ws_id, into=dest_dir)

        # Export each bound subagent
        agent_svc = AgentService()
        subagent_rows = ws_svc.list_subagents(ws_id)
        all_files: list[ExportedFile] = []
        agent_ids: list[str] = []
        for subagent in subagent_rows:
            aid = subagent["agent_id"]
            agent = agent_svc.get_agent_def(aid)
            if agent is None:
                continue
            fmt_str = "claude_code"
            file_pairs = dump_agent(agent, AgentFileFormat(fmt_str))
            agents_dir = dest_dir / "agents"
            for name, content in file_pairs:
                all_files.append(_write_file(agents_dir, name, content))
            agent_ids.append(aid)

        return ExportReport(dest=str(dest_dir), files=all_files, agents=agent_ids)

    def import_agent(self, src_dir: Path) -> ImportReport:
        """Import an agent from src_dir into the DB (dedup-safe).

        Dedup matrix:
          A — name + checksum match  → unchanged
          B — name match, checksum differs → version_added
          C — no name match, checksum match → collision_skipped
          D — no match → created
        """
        # 1. Detect format and read file
        fmt, text, stem = self._detect_agent_file(src_dir)

        # 2. Parse candidate
        candidate = parse_agent(text, fmt, agent_id=stem)

        # 3. Compute checksum
        csum = _checksum(candidate.prompt or "")

        # 4. Build dedup indices
        agent_svc = AgentService()
        agents = agent_svc.list_all_agents()
        by_name = {a.id: a for a in agents}
        by_csum = {_checksum(a.prompt or ""): a for a in agents}

        name_match = by_name.get(candidate.id)
        csum_match = by_csum.get(csum)

        outcome: ImportOutcome
        if name_match is not None and _checksum(name_match.prompt or "") == csum:
            # Case A — identical already in DB
            outcome = ImportOutcome(
                item_id=candidate.id,
                action=ImportAction.unchanged,
            )
        elif name_match is not None:
            # Case B — same name, content differs → new version
            agent_obj = inline_to_composition(candidate)
            config_json: dict = {
                **agent_obj.model_dump(mode="json", exclude_none=True),
                **build_config_json_payload(agent_obj),
            }
            row = agent_svc.add_agent_version(
                agent_id=candidate.id,
                config_json=config_json,
                prompt_content=candidate.prompt,
                author="cli",
                changelog="imported",
            )
            outcome = ImportOutcome(
                item_id=candidate.id,
                action=ImportAction.version_added,
                version=row["version"],
            )
        elif csum_match is not None:
            # Case C — different name, same content → skip to avoid duplicate
            outcome = ImportOutcome(
                item_id=candidate.id,
                action=ImportAction.collision_skipped,
                collision_with=csum_match.id,
            )
        else:
            # Case D — brand new agent
            agent_obj = inline_to_composition(candidate)
            config_json = {
                **agent_obj.model_dump(mode="json", exclude_none=True),
                **build_config_json_payload(agent_obj),
            }
            row = agent_svc.create_agent(
                agent_id=candidate.id,
                config_json=config_json,
                prompt_content=candidate.prompt,
                author="cli",
                changelog="imported",
            )
            outcome = ImportOutcome(
                item_id=candidate.id,
                action=ImportAction.created,
                version=1,
            )

        return ImportReport(source=str(src_dir), outcomes=[outcome])

    def import_skill(self, src_dir: Path) -> ImportReport:
        """Import a skill directory from disk into the DB."""
        slug = src_dir.name
        zip_bytes = _dir_to_zip(src_dir)

        svc = ResourceService()
        existing = svc.get_by_slug(slug)

        outcome: ImportOutcome
        if existing is not None:
            svc.import_zip_version(
                existing["id"],
                filename=f"{slug}.zip",
                content=zip_bytes,
                changelog="imported",
            )
            outcome = ImportOutcome(item_id=slug, action=ImportAction.version_added)
        else:
            row = svc.create_resource(
                slug=slug,
                type=ResourceType.SKILL,
                display_name=slug,
                created_by="cli",
            )
            svc.import_zip_version(
                row["id"],
                filename=f"{slug}.zip",
                content=zip_bytes,
                changelog="imported",
            )
            outcome = ImportOutcome(item_id=slug, action=ImportAction.created)

        return ImportReport(source=str(src_dir), outcomes=[outcome])

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _detect_agent_file(src_dir: Path) -> tuple[AgentFileFormat, str, str]:
        """Detect format, return (fmt, text, stem).

        Detection order:
          1. *.md with 'name' in frontmatter → claude_code
          2. *.md without 'name' → opencode (stem is agent_id)
          3. *.toml → codex (stem is agent_id)
        """
        md_files = list(src_dir.glob("*.md"))
        toml_files = list(src_dir.glob("*.toml"))

        # Check .md files for claude_code frontmatter (has 'name:' key)
        for md_path in md_files:
            text = md_path.read_text(encoding="utf-8")
            # Quick frontmatter check: look for 'name:' inside --- ... ---
            if re.match(r"---\s*\n", text):
                fm_end = text.find("---", 3)
                if fm_end != -1:
                    frontmatter = text[3:fm_end]
                    if re.search(r"^name\s*:", frontmatter, re.MULTILINE):
                        return AgentFileFormat.claude_code, text, md_path.stem

        # .md files without 'name' → opencode
        for md_path in md_files:
            text = md_path.read_text(encoding="utf-8")
            return AgentFileFormat.opencode, text, md_path.stem

        # .toml → codex
        for toml_path in toml_files:
            text = toml_path.read_text(encoding="utf-8")
            return AgentFileFormat.codex, text, toml_path.stem

        raise ValueError(
            f"No agent file found in {src_dir}. Expected *.md (claude_code/opencode) "
            f"or *.toml (codex)."
        )
