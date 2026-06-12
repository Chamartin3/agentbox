"""Workspace-side prep helpers — env-doc rendering, binding resolution,
per-run secrets injection, workspace permissions, and per-run workdir
materialization.

This module is the single owner of all workspace-to-disk projection
logic. Both the save-time path (``build_workspace``) and the per-run
path (``prepare_run_workdir``) delegate here.  Execution code imports
from this module; the reverse direction is forbidden.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from agentbox.core.resources.workspace_materialize import materialize_workspace
from agentbox.core.workspaces.env_doc.renderers.agents_md import AgentsMdRenderer
from agentbox.core.workspaces.env_doc.renderers.base import RuntimeContext
from agentbox.core.workspaces.env_doc.renderers.claude_md import ClaudeMdRenderer
from agentbox.core.workspaces.env_doc.schema import EnvDocContent
from agentbox.core.workspaces.generation.engine_config import make_generator
from agentbox.core.workspaces.generation.materialize import materialize_subagents

if TYPE_CHECKING:
    from agentbox.config import Settings
    from agentbox.core.data import AgentDef, RunStore, WorkspaceBuildStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workspace resource resolution
# ---------------------------------------------------------------------------


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
        if version is None:
            logger.warning(
                "workspace prep: version %s not found — skipping workspace binding %s",
                version_id,
                b["id"],
            )
            continue
        blobs = list(store.iter_repo_blobs(version_id))
        source_metadata: dict = {}
        raw_meta = version.get("source_metadata")
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


# ---------------------------------------------------------------------------
# Workspace subagent resolution
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Env-doc rendering
# ---------------------------------------------------------------------------


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


def prompt_resolution_to_snapshot(resolution: Any) -> list[dict]:
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


# ---------------------------------------------------------------------------
# Agent prompt binding resolution
# ---------------------------------------------------------------------------


def resolve_agent_prompt_bindings(store: RunStore, agent_id: str) -> list[dict]:
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
                "workspace prep: prompt binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if version_id:
            version_id = str(version_id)
        if not version_id:
            active = store.get_active_repo_version(b["resource_id"])
            if not active:
                logger.warning(
                    "workspace prep: resource %s has no active version — skipping prompt binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = str(active["id"])
        version = store.get_repo_version(version_id)
        if version is None:
            continue
        blobs = list(store.iter_repo_blobs(version_id))
        resolved.append(
            {
                "binding_id": b["id"],
                "marker": b.get("marker"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "resource_id": b["resource_id"],
                "version_id": version_id,
                "content_hash": version["content_hash"],
                "type": resource["type"],
                "mode": b.get("mode"),
                "display_name": resource["display_name"],
                "required": bool(b.get("required", 1)),
                "blobs": blobs,
            }
        )
    return resolved


# ---------------------------------------------------------------------------
# Workspace permission resolution
# ---------------------------------------------------------------------------


def load_workspace_permissions(
    workdir: Path,
    agent: AgentDef,
    settings: Settings,
    store: WorkspaceBuildStore | None = None,
) -> dict:
    """Resolve effective workspace permissions from the DB overlay.

    ``workspace_runtime_permissions`` is the single source of truth for
    built-in tools, file scopes, max_tokens, and network/write flags.
    Workspaces with no overlay row receive an empty permissions dict —
    callers downstream treat that as "no constraints declared".
    """
    if not agent.workspace or agent.workspace == "<ephemeral>":
        return {}
    if store is None:
        return {}
    try:
        overlay = store.get_workspace_runtime_permissions(agent.workspace)
    except Exception:
        return {}
    if not overlay:
        return {}
    perms: dict = {}
    if overlay.get("allowed_builtin_tools") is not None:
        perms["allowed_builtin_tools"] = overlay["allowed_builtin_tools"]
    if overlay.get("files") is not None:
        perms["files"] = overlay["files"]
    if overlay.get("max_tokens") is not None:
        perms["max_tokens"] = overlay["max_tokens"]
    if overlay.get("allow_file_write") is not None:
        perms["allow_file_write"] = bool(overlay["allow_file_write"])
    if overlay.get("allow_network") is not None:
        perms["allow_network"] = bool(overlay["allow_network"])
    return perms


# ---------------------------------------------------------------------------
# Per-run workdir preparation (consolidated entry point)
# ---------------------------------------------------------------------------


def prepare_run_workdir(
    *,
    store: RunStore,
    settings: Settings,
    workspace_id: str | None,
    agent: AgentDef,
    workdir: Path,
    mcp_registry: Any = None,
) -> tuple[Path, list[dict]]:
    """Project workspace state into a fresh per-run run dir.

    Steps:
      1. Render the env-doc (CLAUDE.md / AGENTS.md) into ``workdir``.
      2. Materialize workspace resource bindings into ``workdir``.
      3. Materialize workspace subagents into ``workdir``.
      4. Create a fresh ``run_dir`` (UUID-keyed under ``settings.runs_tmpfs_dir``).
      5. Apply the workspace permission overlay (``generate_configs_into``).

    Returns ``(run_dir, resource_snapshot_entries)``.
    The executor materializes the renderer's file dict into ``run_dir``
    separately (see ``execution/orchestrate/materialize.py``).

    Replaces:
    - ``RunSetup.render_for_run``
    - ``execution/prepare/envdoc.py:render_env_doc``
    - ``execution/prepare/resources.py:prepare_run_resources`` (resource side)
    """

    resource_snapshot_entries: list[dict] = []

    # ── 1. Workspace resources, env-doc, subagents ────────────────────────
    if workspace_id and workspace_id != "<ephemeral>":
        try:
            ws_bindings = resolve_workspace_resources(store, workspace_id)
            if ws_bindings:
                outcomes = materialize_workspace(
                    workdir,
                    ws_bindings,
                    cache_root=settings.resource_cache_dir,
                )
                resource_snapshot_entries.extend(workspace_outcomes_to_snapshot(outcomes))
        except Exception:
            logger.exception(
                "prepare_run_workdir: workspace resource materialization failed for workspace %r",
                workspace_id,
            )

        try:
            env_doc_entries = render_env_doc(store, workspace_id, workdir)
            resource_snapshot_entries.extend(env_doc_entries)
        except Exception:
            logger.exception(
                "prepare_run_workdir: env doc rendering failed for workspace %r",
                workspace_id,
            )

        try:
            resolved_subagents = resolve_workspace_subagents(store, workspace_id)
            if resolved_subagents:
                sub_outcomes = materialize_subagents(workdir, resolved_subagents)
                for o in sub_outcomes:
                    resource_snapshot_entries.append(
                        {
                            "role": "workspace_subagent",
                            "workspace_id": o.workspace_id,
                            "agent_id": o.agent_id,
                            "alias": o.alias,
                            "files_written": o.files_written,
                        }
                    )
        except Exception:
            logger.exception(
                "prepare_run_workdir: workspace subagent materialization failed for workspace %r",
                workspace_id,
            )

    # ── 2. Create fresh run_dir ───────────────────────────────────────────
    run_dir = settings.runs_tmpfs_dir / uuid.uuid4().hex
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)

    # ── 3. Apply workspace permission overlay ─────────────────────────────
    permissions = load_workspace_permissions(workdir, agent, settings, store)
    generator = make_generator(
        settings=settings, store=store, mcp_registry=mcp_registry
    )
    generator.generate_configs_into(
        run_dir,
        allowed_builtin_tools=permissions.get("allowed_builtin_tools") or [],
        files=permissions.get("files") or [],
        project_root=settings.project_root,
    )

    return run_dir, resource_snapshot_entries


# ---------------------------------------------------------------------------
# Per-run secrets injection
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
