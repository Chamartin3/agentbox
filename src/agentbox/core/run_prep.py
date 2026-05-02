"""Pre-run preparation helpers for the executor (Phase 1, Plan 08).

These functions compose the resolvers, materializers, and renderers that
already exist in separate modules and plug into the executor's prepare
seam — after _prepare_workdir, before the backend adapter is called.

All functions are pure-ish: they read from ``store`` and the filesystem
but never write to the store. Snapshot persistence is the executor's job.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data.store import SessionStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workspace resource resolution
# ---------------------------------------------------------------------------


def resolve_workspace_resources(store: SessionStore, workspace_id: str) -> list[dict]:
    """Hydrate all active workspace file bindings into materializer-ready dicts.

    Returns the same shape as ``_resolve_binding_for_prompt`` in the API
    route, so ``materialize_workspace`` can consume them directly.
    Returns an empty list when workspace_id is None / ephemeral or when no
    bindings exist.
    """
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
                "run_prep: workspace binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if not version_id:
            active = store.get_active_repo_version(b["resource_id"])
            if not active:
                logger.warning(
                    "run_prep: resource %s has no active version — skipping workspace binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = active["id"]
        version = store.get_repo_version(version_id)
        blobs = list(store.iter_repo_blobs(version_id))
        resolved.append(
            {
                "binding_id": b["id"],
                "resource_id": b["resource_id"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "display_name": resource["display_name"],
                "target_path": b.get("target_path"),
                "materialize_mode": b.get("materialize_mode", "copy"),
                "on_conflict": b.get("on_conflict", "error"),
                "blobs": blobs,
                "skill_meta": None,
            }
        )
    return resolved


# ---------------------------------------------------------------------------
# Agent prompt binding resolution
# ---------------------------------------------------------------------------


def resolve_agent_prompt_bindings(store: SessionStore, agent_id: str) -> list[dict]:
    """Hydrate all active prompt bindings for an agent into resolver-ready dicts.

    Returns the same shape as ``_resolve_binding_for_prompt`` in the API
    route, so ``resolve_prompt`` can consume them directly.
    """
    bindings = store.list_prompt_bindings(agent_id)
    if not bindings:
        return []

    resolved: list[dict] = []
    for b in bindings:
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            logger.warning(
                "run_prep: prompt binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if not version_id:
            active = store.get_active_repo_version(b["resource_id"])
            if not active:
                logger.warning(
                    "run_prep: resource %s has no active version — skipping prompt binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = active["id"]
        version = store.get_repo_version(version_id)
        blobs = list(store.iter_repo_blobs(version_id))
        resolved.append(
            {
                "binding_id": b["id"],
                "marker": b["marker"],
                "resource_id": b["resource_id"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "mode": b["mode"],
                "display_name": resource["display_name"],
                "required": bool(b.get("required", 1)),
                "blobs": blobs,
            }
        )
    return resolved


# ---------------------------------------------------------------------------
# Env-doc rendering
# ---------------------------------------------------------------------------


def render_env_doc(
    store: SessionStore,
    workspace_id: str,
    workdir: Path,
) -> list[dict]:
    """Render the active env doc into CLAUDE.md and AGENTS.md in ``workdir``.

    Returns a list of snapshot entry dicts (role="env_doc"). Returns empty
    list when no active env doc exists for the workspace.
    """
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
            logger.warning("run_prep: env doc version %s has invalid content_json", doc.get("id"))
            return []

    from agentbox.core.env_doc.renderers.agents_md import AgentsMdRenderer
    from agentbox.core.env_doc.renderers.base import RuntimeContext
    from agentbox.core.env_doc.renderers.claude_md import ClaudeMdRenderer
    from agentbox.core.env_doc.schema import EnvDocContent

    try:
        content = EnvDocContent.model_validate(content_json)
    except Exception:
        logger.warning("run_prep: could not parse env doc content for workspace %s", workspace_id)
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


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


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


def prompt_resolution_to_snapshot(resolution) -> list[dict]:
    """Convert PromptResolution snapshot list to JSON-serializable entries."""
    entries = []
    for rb in resolution.snapshot:
        entries.append(
            {
                "role": "prompt_embed",
                "binding_id": rb.binding_id,
                "marker": rb.marker,
                "resource_id": rb.resource_id,
                "version_id": rb.version_id,
                "content_hash": rb.content_hash,
                "mode": rb.mode,
            }
        )
    return entries
