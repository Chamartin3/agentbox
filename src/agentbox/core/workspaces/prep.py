"""Workspace-side prep helpers — env-doc rendering, binding resolution,
and per-run secrets injection.

Hosted here (rather than under ``core/run/``) so ``core/workspace/`` no
longer needs to import from ``core/run/``. Run-side prep imports these;
the reverse direction is gone.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from agentbox.core.workspaces.env_doc.renderers.agents_md import AgentsMdRenderer
from agentbox.core.workspaces.env_doc.renderers.base import RuntimeContext
from agentbox.core.workspaces.env_doc.renderers.claude_md import ClaudeMdRenderer
from agentbox.core.workspaces.env_doc.schema import EnvDocContent

if TYPE_CHECKING:
    from agentbox.core.data import WorkspaceBuildStore

logger = logging.getLogger(__name__)


def resolve_workspace_resources(store: WorkspaceBuildStore, workspace_id: str) -> list[dict]:
    """Hydrate all active workspace file bindings into materializer-ready dicts."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return []

    bindings = store.list_workspace_file_bindings(workspace_id)
    if not bindings:
        return []

    resolved: list[dict] = []
    for b in bindings:
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            logger.warning(
                "workspace prep: workspace binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if not version_id:
            active = store.get_active_repo_version(b["resource_id"])
            if not active:
                logger.warning(
                    "workspace prep: resource %s has no active version — skipping workspace binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = active["id"]
        version = store.get_repo_version(version_id)
        blobs = list(store.iter_repo_blobs(version_id))
        source_metadata: dict = {}
        raw_meta = version.get("source_metadata") if version else None
        if raw_meta:
            if isinstance(raw_meta, str):
                try:
                    source_metadata = json.loads(raw_meta)
                except Exception:
                    source_metadata = {}
            elif isinstance(raw_meta, dict):
                source_metadata = raw_meta
        resolved.append(
            {
                "binding_id": b["id"],
                "resource_id": b["resource_id"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "slug": resource["slug"],
                "display_name": resource["display_name"],
                "target_path": b.get("target_path"),
                "materialize_mode": b.get("materialize_mode", "copy"),
                "on_conflict": b.get("on_conflict", "error"),
                "blobs": blobs,
                "skill_meta": None,
                "source_metadata": source_metadata,
            }
        )
    return resolved


def resolve_workspace_subagents(store: WorkspaceBuildStore, workspace_id: str) -> list[dict]:
    """Hydrate workspace subagent rows into renderer-ready dicts."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return []

    rows = store.list_workspace_subagents(workspace_id)
    if not rows:
        return []

    resolved: list[dict] = []
    for r in rows:
        agent_id = r["agent_id"]
        active = store.get_active_version(agent_id)
        prompt = (active or {}).get("prompt_content") or (active or {}).get(
            "prompt_snapshot"
        )
        if not prompt:
            logger.warning(
                "workspace prep: subagent %s for workspace %s — agent %s has no "
                "active prompt content; skipping",
                r.get("alias"),
                workspace_id,
                agent_id,
            )
            continue
        agent_def = store.get_agent_def(agent_id)
        resolved.append(
            {
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "alias": r["alias"],
                "description": getattr(agent_def, "description", None)
                if agent_def
                else None,
                "prompt_content": prompt,
            }
        )
    return resolved


def render_env_doc(
    store: WorkspaceBuildStore,
    workspace_id: str,
    workdir: Path,
) -> list[dict]:
    """Render the active env doc into CLAUDE.md and AGENTS.md in ``workdir``."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return []

    doc = store.get_active_env_doc(workspace_id)
    if not doc:
        return []

    content_json = doc.get("content_json") or {}
    if isinstance(content_json, str):
        try:
            content_json = json.loads(content_json)
        except Exception:
            logger.warning(
                "workspace prep: env doc version %s has invalid content_json",
                doc.get("id"),
            )
            return []

    try:
        content = EnvDocContent.model_validate(content_json)
    except Exception:
        logger.warning(
            "workspace prep: could not parse env doc content for workspace %s",
            workspace_id,
        )
        return []

    ctx = RuntimeContext()
    claude_text = ClaudeMdRenderer().render(content, ctx)
    agents_text = AgentsMdRenderer().render(content, ctx)

    snapshot_entries: list[dict] = []
    for filename, text, audience in (
        ("CLAUDE.md", claude_text, "claude_only"),
        ("AGENTS.md", agents_text, "agents_only"),
    ):
        dest = workdir / filename
        dest.write_text(text, encoding="utf-8")
        snapshot_entries.append(
            {
                "role": "env_doc",
                "file": filename,
                "workspace_id": workspace_id,
                "env_doc_version_id": doc["id"],
                "audience": audience,
                "bytes": len(text.encode()),
            }
        )
    return snapshot_entries


def workspace_outcomes_to_snapshot(outcomes: list) -> list[dict]:
    """Convert MaterializeOutcome list to JSON-serializable snapshot entries."""
    entries = []
    for o in outcomes:
        entries.append(
            {
                "role": "workspace_file",
                "binding_id": o.binding_id,
                "resource_id": o.resource_id,
                "version_id": o.version_id,
                "content_hash": o.content_hash,
                "target_path": o.target_path,
                "files_written": o.files_written,
                "mode": o.mode,
                "skipped": o.skipped,
                "skipped_reason": o.skipped_reason,
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Per-run secrets injection (APP-DEP: Runs → Workspaces contract)
# ---------------------------------------------------------------------------


def write_secrets(
    workdir: Path,
    secrets: Mapping[str, str],
) -> None:
    """Write opaque secrets into ``<workdir>/.agentbox/secrets.env``.

    Workspaces never inspects the key names or values — this is a pure
    I/O operation. The ``.env`` format is consumed by CLI backends
    (Claude Code, OpenCode, etc.) that source the file at startup.
    """
    if not secrets:
        return
    secrets_dir = workdir / ".agentbox"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    env_path = secrets_dir / "secrets.env"
    tmp_path = env_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for key, value in secrets.items():
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            f.write(f'{key}="{escaped}"\n')
    shutil.move(str(tmp_path), str(env_path))
