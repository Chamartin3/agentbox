"""Manifest editor — round-trips agentbox.toml through tomlkit.

Preserves comments and formatting; rejects patches that would produce
an invalid AgentDef. Writes are atomic (tmp + rename).

Dispatch by ``source_format``:
- ``INLINE_TOML``: edit the ``[[agents]]`` block in ``agentbox.toml``.
- ``STANDALONE_TOML``: write a standalone ``.toml`` file.
- ``MARKDOWN``: write a markdown file with YAML frontmatter.
- ``LEGACY_DIR``: write agent.toml + prompts/system.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import tomlkit
from tomlkit.items import AoT, Table

from agentbox.core.data.manifest import AgentDef, AgentSource, ProjectManifest
from agentbox.core.definitions.manifest_writer_toml import (
    _atomic_write,
    _build_runner_table,
    write_legacy_dir,
    write_standalone_toml,
)
from agentbox.core.definitions.markdown import write_markdown_agent

# Fields that may be edited via PATCH /manifest/agents/{id}.
_AGENT_PATCHABLE = {
    "description",
    "session_mode",
    "workspace",
    "tags",
    "tools",
    "webhook_url",
    "headless",
    "guardrails",
    "prompt",
    "prompt_path",
}
_RUNNER_PATCHABLE = {
    "kind",
    "model",
    "agent_module",
    "mcp_config_path",
    "agents_config_path",
    "settings_path",
    "config_path",
    "allowed_tools",
    "extra_args",
    "timeout_seconds",
    "command",
    "output_schema_path",
    "max_validation_retries",
}


@dataclass
class PatchError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.detail}"


class ManifestWriter:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    @property
    def path(self) -> Path:
        new = self.project_root / "manifest.toml"
        if new.exists():
            return new
        return self.project_root / "agentbox.toml"

    def read_text(self) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    def read_parsed(self) -> ProjectManifest:
        if not self.path.exists():
            return ProjectManifest()
        data = tomlkit.parse(self.read_text())
        return ProjectManifest.model_validate(_to_plain(data))

    def save_agent(self, agent: AgentDef) -> Path:
        """Persist an ``AgentDef`` to its source file, dispatching by format.

        Returns the path written to.
        """
        fmt = agent.source_format

        if fmt == AgentSource.MARKDOWN:
            return self._save_markdown(agent)
        if fmt == AgentSource.STANDALONE_TOML:
            return self._save_standalone_toml(agent)
        if fmt == AgentSource.LEGACY_DIR:
            return self._save_legacy_dir(agent)

        # INLINE_TOML or unknown → fall back to inline edit
        return self._save_inline(agent)

    def _save_markdown(self, agent: AgentDef) -> Path:
        path = agent.source_path or self.project_root / "agents.d" / f"{agent.id}.md"
        existing_metadata = None
        if path.exists():
            existing_metadata = dict(frontmatter.load(str(path)).metadata)
        write_markdown_agent(
            path, agent, preserve_unknown_keys=True, existing_metadata=existing_metadata
        )
        return path

    def _save_standalone_toml(self, agent: AgentDef) -> Path:
        path = agent.source_path or self.project_root / "agents.d" / f"{agent.id}.toml"
        write_standalone_toml(path, agent)
        return path

    def _save_legacy_dir(self, agent: AgentDef) -> Path:
        if agent.source_path:
            agent_dir = (
                agent.source_path.parent
                if agent.source_path.suffix == ".toml"
                else agent.source_path
            )
        else:
            agent_dir = self.project_root / "agents" / agent.id
        write_legacy_dir(agent_dir, agent)
        return agent_dir / "agent.toml"

    def _save_inline(self, agent: AgentDef) -> Path:
        """Write or update an inline ``[[agents]]`` block in ``agentbox.toml``."""
        path = self.path
        if not path.exists():
            doc = tomlkit.document()
            doc["agents"] = tomlkit.array()
            doc["agents"].multiline(True)
        else:
            doc = tomlkit.parse(path.read_text(encoding="utf-8"))

        agents = doc.get("agents")
        if not isinstance(agents, AoT):
            agents = tomlkit.aot()
            doc["agents"] = agents

        existing = _find_agent_table(agents, agent.id)
        if existing is not None:
            idx = agents.index(existing)
            agents[idx] = _agent_to_table(agent)
        else:
            agents.append(_agent_to_table(agent))

        new_text = tomlkit.dumps(doc)
        _atomic_write(path, new_text)
        return path

    def patch_agent(self, agent_id: str, patch: dict[str, Any]) -> AgentDef:
        """Apply a patch to one agent. Returns the updated AgentDef.

        Raises PatchError on unknown agent, forbidden field, or validation failure.

        Handles both inline ``[[agents]]`` blocks in the top-level manifest
        and standalone bundle ``agent.toml`` files. For bundle agents the
        edit is applied directly to the bundle TOML.
        """
        if self.path.exists():
            doc = tomlkit.parse(self.read_text())
            agents = doc.get("agents")
            if isinstance(agents, AoT):
                target_table = _find_agent_table(agents, agent_id)
                if target_table is not None:
                    return self._patch_inline(doc, target_table, agent_id, patch)

        # Fall back to a bundle agent.toml.
        return self._patch_bundle(agent_id, patch)

    def _patch_bundle(self, agent_id: str, patch: dict[str, Any]) -> AgentDef:
        from agentbox.api.deps import get_loader

        loader = get_loader()
        agent = loader.get(agent_id)
        if agent is None or not agent.source_path:
            raise PatchError("unknown_agent", f"no agent with id={agent_id!r}")
        src = Path(agent.source_path)
        if src.is_dir():
            src = src / "agent.toml"
        if not src.exists() or src.suffix != ".toml":
            raise PatchError(
                "unsupported_source",
                f"bundle agent {agent_id!r} has no editable agent.toml at {src}",
            )

        doc = tomlkit.parse(src.read_text(encoding="utf-8"))
        _apply_patch(doc, patch)

        # Re-parse the bundle through AgentDef to validate.
        try:
            from agentbox.core.data.manifest import AgentDef as _AgentDef

            updated = _AgentDef.model_validate(_to_plain(doc))
        except Exception as exc:
            raise PatchError("validation_failed", str(exc)) from exc

        _atomic_write(src, tomlkit.dumps(doc))
        # Carry over source metadata that wasn't in the bundle TOML.
        updated.source_path = agent.source_path
        updated.source_format = agent.source_format
        return updated

    def _patch_inline(
        self,
        doc: Any,
        target_table: Table,
        agent_id: str,
        patch: dict[str, Any],
    ) -> AgentDef:

        _apply_patch(target_table, patch)

        # Validate the entire manifest by re-parsing through pydantic.
        # If it fails, do NOT write — surface the validation error.
        try:
            parsed = ProjectManifest.model_validate(_to_plain(doc))
        except Exception as exc:
            raise PatchError("validation_failed", str(exc)) from exc

        # Atomic write.
        new_text = tomlkit.dumps(doc)
        _atomic_write(self.path, new_text)

        for a in parsed.agents:
            if a.id == agent_id:
                return a
        raise PatchError("post_validate", "agent missing after re-parse")


def _find_agent_table(agents: AoT, agent_id: str) -> Table | None:
    for entry in agents:
        if isinstance(entry, Table) and entry.get("id") == agent_id:
            return entry
    return None


def _apply_patch(table: Table, patch: dict[str, Any]) -> None:
    runner_patch = patch.get("runner") or {}
    for k, v in patch.items():
        if k == "runner":
            continue
        if k == "id":
            raise PatchError("forbidden_field", "cannot change agent id")
        if k not in _AGENT_PATCHABLE:
            raise PatchError("forbidden_field", f"field {k!r} is not editable")
        if v is None:
            if k in table:
                del table[k]
        else:
            table[k] = v

    if runner_patch:
        runner_tbl = table.get("runner")
        if not isinstance(runner_tbl, Table):
            raise PatchError("no_runner", "agent has no [agents.runner] table")
        for k, v in runner_patch.items():
            if k not in _RUNNER_PATCHABLE:
                raise PatchError("forbidden_field", f"runner.{k} is not editable")
            if v is None:
                if k in runner_tbl:
                    del runner_tbl[k]
            else:
                runner_tbl[k] = v


def _agent_to_table(agent: AgentDef) -> Table:
    """Convert an ``AgentDef`` to a tomlkit ``Table`` for inline storage."""
    t = tomlkit.table()
    t["id"] = agent.id
    if agent.description:
        t["description"] = agent.description
    if agent.workspace:
        t["workspace"] = agent.workspace
    if agent.tools:
        t["tools"] = tomlkit.array()
        t["tools"].extend(agent.tools)
    if agent.tags:
        t["tags"] = tomlkit.array()
        t["tags"].extend(agent.tags)
    if agent.session_mode != "headless":
        t["session_mode"] = agent.session_mode
    if not agent.claude_agent:
        t["claude_agent"] = False
    if agent.headless:
        t["headless"] = True
    if agent.webhook_url:
        t["webhook_url"] = agent.webhook_url
    if agent.unsupported_backends:
        t["unsupported_backends"] = tomlkit.array()
        t["unsupported_backends"].extend(agent.unsupported_backends)
    if agent.prompt:
        t["prompt"] = agent.prompt
    elif agent.prompt_path:
        t["prompt_path"] = agent.prompt_path

    t["runner"] = _build_runner_table(agent.runner)
    return t


def _to_plain(doc: Any) -> Any:
    """Convert a tomlkit document to plain dict/list for pydantic validation."""
    if isinstance(doc, dict):
        return {k: _to_plain(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_to_plain(v) for v in doc]
    # tomlkit scalar items behave like their underlying Python types; unwrap.
    if hasattr(doc, "unwrap"):
        return doc.unwrap()
    return doc
