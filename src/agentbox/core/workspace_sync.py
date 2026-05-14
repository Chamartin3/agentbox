"""Workspace sync orchestrator (Plan: interactive-sessions Phase 1).

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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.resources.subagent_render import materialize_subagents
from agentbox.core.resources.workspace_materialize import materialize_workspace
from agentbox.core.run_prep import (
    render_env_doc,
    resolve_workspace_resources,
    resolve_workspace_subagents,
    workspace_outcomes_to_snapshot,
)

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data.store import SessionStore

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
    import shutil

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
        logger.exception("workspace_sync: failed to remove orphan %s", target)
        return False


def sync_workspace(
    store: SessionStore,
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

    try:
        ws_bindings = resolve_workspace_resources(store, workspace_id)
        if ws_bindings:
            # Sync runs on every launch + every save against a persistent
            # workspace, so the per-binding ``on_conflict`` semantics
            # (designed for one-shot run dirs) need to be overridden.
            # The DB binding is the source of truth — overwrite stale
            # on-disk copies unless the binding explicitly opted into
            # ``skip``.
            for b in ws_bindings:
                if b.get("on_conflict", "error") != "skip":
                    b["on_conflict"] = "overwrite"
            outcomes = materialize_workspace(
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
            # Keep the snapshot conversion as a side effect for callers
            # that want to merge into a run snapshot.
            workspace_outcomes_to_snapshot(outcomes)
    except Exception as e:
        logger.exception(
            "workspace_sync: resource materialization failed for %r", workspace_id
        )
        result.errors.append(f"resources: {e}")

    try:
        env_entries = render_env_doc(store, workspace_id, workdir)
        result.env_doc_files = [e["file"] for e in env_entries]
    except Exception as e:
        logger.exception(
            "workspace_sync: env doc rendering failed for %r", workspace_id
        )
        result.errors.append(f"env_doc: {e}")

    try:
        resolved_subagents = resolve_workspace_subagents(store, workspace_id)
        if resolved_subagents:
            sub_outcomes = materialize_subagents(workdir, resolved_subagents)
            result.subagents_written = [o.alias for o in sub_outcomes]
    except Exception as e:
        logger.exception(
            "workspace_sync: subagent materialization failed for %r", workspace_id
        )
        result.errors.append(f"subagents: {e}")

    # Orphan cleanup — remove on-disk paths that were materialized in a
    # prior sync but are no longer produced by any current binding. Only
    # paths recorded in the previous meta.json are eligible — we never
    # touch files agentbox didn't materialize.
    current_paths = set(result.materialized_paths)
    for orphan in sorted(previous_paths - current_paths):
        if _remove_orphan(workdir, orphan):
            result.orphans_removed.append(orphan)

    _write_provenance(workdir, result)
    return result


def resolve_workspace_workdir(
    store: SessionStore, settings: Settings, workspace_id: str
) -> Path | None:
    """Resolve a workspace name → on-disk workdir path.

    Tries the DB workspace record's ``path`` first; falls back to
    ``settings.workspaces_root / workspace_id`` if the record has no
    explicit path. Returns ``None`` for unknown or ephemeral workspaces.
    """
    if not workspace_id or workspace_id == "<ephemeral>":
        return None
    record = store.get_workspace(workspace_id)
    if record is not None and record.get("path"):
        rel = record["path"]
        return (settings.project_root / rel).resolve()
    candidate = settings.workspaces_root / workspace_id
    return candidate if candidate.exists() else None


def sync_workspace_by_name(
    store: SessionStore, settings: Settings, workspace_id: str
) -> WorkspaceSyncResult | None:
    """Convenience wrapper: resolve workdir from name, then sync.

    Returns ``None`` when the workspace has no resolvable workdir
    (unknown name, ephemeral, or path missing).
    """
    workdir = resolve_workspace_workdir(store, settings, workspace_id)
    if workdir is None:
        return None
    return sync_workspace(store, settings, workspace_id, workdir)


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
