"""Workspace sync orchestrator.

A single entrypoint that materializes the full workspace context onto
disk: env-doc (CLAUDE.md / AGENTS.md), per-provider subagent files,
and resource bindings. Callable from save-time API endpoints, from
``agentbox launch``, and from the executor's run-prep path.

The orchestrator does NOT decide file layout for resource bindings —
that's owned by each binding's ``target_path`` / ``materialize_mode``.
This module only sequences the existing renderers and writes a
provenance file at ``<workdir>/.agentbox/meta.json`` summarizing what
was rendered and when.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.db import (
    AgentDefManager,
    AgentVersionManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceFileResourceBindingManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceManager,
    WorkspaceSubagentManager,
)
from agentbox.core.workspaces.generation.builders.from_db import load_workenv
from agentbox.core.workspaces.construct import workspace_constructor
from agentbox.core.workspaces.prep import (
    render_env_doc,
    resolve_workspace_resources,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceSyncResult:
    workspace_id: str
    workdir: Path
    env_doc_files: list[str] = field(default_factory=list)
    subagents_written: list[str] = field(default_factory=list)
    bindings_materialized: int = 0
    bindings_skipped: int = 0
    materialized_paths: list[str] = field(default_factory=list)
    orphans_removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _read_previous_meta(workdir: Path) -> dict:
    meta_path = workdir / ".agentbox" / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _remove_orphan(workdir: Path, rel_path: str) -> bool:
    """Best-effort remove an on-disk path. Returns True if anything was removed."""
    if not rel_path:
        return False
    target = (workdir / rel_path).resolve()
    if not str(target).startswith(str(workdir.resolve())):
        return False  # path escaped workdir — refuse
    if not target.exists() and not target.is_symlink():
        return False
    try:
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
        return True
    except Exception:
        logger.exception("workspace_build: failed to remove orphan %s", target)
        return False


def build_workspace(
    workspaces: WorkspaceManager,
    agent_defs: AgentDefManager,
    workspace_subagents: WorkspaceSubagentManager,
    agent_versions: AgentVersionManager,
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    workspace_mcp_overrides: WorkspaceMcpOverrideManager,
    workspace_mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    workspace_env_doc_versions: WorkspaceEnvDocVersionManager,
    settings: Settings,
    workspace_id: str,
    workdir: Path,
) -> WorkspaceSyncResult:
    """Materialize the workspace's full disk state.

    Sequence (matches the executor's run-prep path):
      1. Materialize resource bindings (binds files into workdir).
      2. Render env-doc (CLAUDE.md / AGENTS.md).
      3. Materialize subagents (per-provider agents dirs).
      4. Write provenance to ``<workdir>/.agentbox/meta.json``.

    Each step is best-effort: a failure in one is logged and recorded
    in ``result.errors`` but does not block the next step.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    result = WorkspaceSyncResult(workspace_id=workspace_id, workdir=workdir)

    if not workspace_id or workspace_id == "<ephemeral>":
        return result

    previous_meta = _read_previous_meta(workdir)
    previous_paths: set[str] = set(previous_meta.get("materialized_paths") or [])

    constructor = workspace_constructor()

    try:
        ws_bindings = resolve_workspace_resources(
            workspace_file_resource_bindings,
            resources,
            resource_versions,
            resource_blobs,
            workspace_id,
        )
        if ws_bindings:
            # Sync runs on every launch + every save against a persistent
            # workspace, so the per-binding ``on_conflict`` semantics
            # (designed for one-shot run dirs) need to be overridden.
            for b in ws_bindings:
                if b.get("on_conflict", "error") != "skip":
                    b["on_conflict"] = "overwrite"
            outcomes = constructor.materialize(
                workdir,
                ws_bindings,
                cache_root=settings.resource_cache_dir,
            )
            for o in outcomes:
                if getattr(o, "skipped", False):
                    result.bindings_skipped += 1
                else:
                    result.bindings_materialized += 1
                if o.target_path:
                    result.materialized_paths.append(o.target_path)
    except Exception as e:
        logger.exception(
            "workspace_build: resource materialization failed for %r", workspace_id
        )
        result.errors.append(f"resources: {e}")

    try:
        env_entries = render_env_doc(workspace_env_doc_versions, workspace_id, workdir)
        result.env_doc_files = [e["file"] for e in env_entries]
    except Exception as e:
        logger.exception(
            "workspace_build: env doc rendering failed for %r", workspace_id
        )
        result.errors.append(f"env_doc: {e}")

    try:
        config = load_workenv(
            workspaces,
            agent_defs,
            workspace_subagents,
            agent_versions,
            workspace_file_resource_bindings,
            workspace_mcp_overrides,
            workspace_mcp_tool_overrides,
            workspace_env_doc_versions,
            workspace_id,
            settings=settings,
        )
        subagents = [a for a in config.agents if a.role != "main"]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Render every engine's full config into a throwaway dir, then
            # copy just the subagent files into the persistent workdir.
            constructor.generate(tmp_dir, config)
            for recipe in constructor.recipes:
                for a in subagents:
                    rel = recipe.resolve_layout("subagent", name=a.id)
                    if not rel:
                        continue
                    src = tmp_dir / rel
                    if src.is_file():
                        dst = workdir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
        result.subagents_written = [a.id for a in subagents]
    except Exception as e:
        logger.exception(
            "workspace_build: subagent materialization failed for %r", workspace_id
        )
        result.errors.append(f"subagents: {e}")

    # Orphan cleanup
    current_paths = set(result.materialized_paths)
    for orphan in sorted(previous_paths - current_paths):
        if _remove_orphan(workdir, orphan):
            result.orphans_removed.append(orphan)

    _write_provenance(workdir, result)
    return result


def resolve_workspace_workdir(
    workspaces: WorkspaceManager,
    settings: Settings,
    workspace_id: str,
) -> Path | None:
    """Resolve a workspace name → on-disk workdir path."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return None
    record = workspaces.get_by_name(workspace_id)
    if record is not None:
        rel = record.get("path")
        if rel:
            return (settings.project_root / rel).resolve()
    candidate = settings.workspaces_root / workspace_id
    return candidate if candidate.exists() else None


def build_workspace_by_name(
    workspaces: WorkspaceManager,
    agent_defs: AgentDefManager,
    workspace_subagents: WorkspaceSubagentManager,
    agent_versions: AgentVersionManager,
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    workspace_mcp_overrides: WorkspaceMcpOverrideManager,
    workspace_mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    workspace_env_doc_versions: WorkspaceEnvDocVersionManager,
    settings: Settings,
    workspace_id: str,
) -> WorkspaceSyncResult | None:
    """Convenience wrapper: resolve workdir from name, then sync."""
    workdir = resolve_workspace_workdir(workspaces, settings, workspace_id)
    if workdir is None:
        return None
    return build_workspace(
        workspaces,
        agent_defs,
        workspace_subagents,
        agent_versions,
        workspace_file_resource_bindings,
        resources,
        resource_versions,
        resource_blobs,
        workspace_mcp_overrides,
        workspace_mcp_tool_overrides,
        workspace_env_doc_versions,
        settings,
        workspace_id,
        workdir,
    )


def _write_provenance(workdir: Path, result: WorkspaceSyncResult) -> None:
    meta_dir = workdir / ".agentbox"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "workspace_id": result.workspace_id,
        "synced_at": datetime.now(UTC).isoformat(),
        "env_doc_files": result.env_doc_files,
        "subagents_written": result.subagents_written,
        "bindings_materialized": result.bindings_materialized,
        "bindings_skipped": result.bindings_skipped,
        "materialized_paths": result.materialized_paths,
        "orphans_removed": result.orphans_removed,
        "errors": result.errors,
    }
    (meta_dir / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
