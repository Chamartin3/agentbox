"""Workspace-side prep helpers — env-doc rendering, binding resolution,
per-run secrets injection, workspace permissions, and per-run workdir
materialization.

This module is the single owner of all workspace-to-disk projection
logic. Both the save-time path (``build_workspace``) and the per-run
path (``prepare_run_workdir``) delegate here.  Execution code imports
from this module; the reverse direction is forbidden.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import (
    EnvDocRenderEntry,
    PromptEmbedSnapshotEntry,
    RunSnapshotEntry,
    WorkspaceFileSnapshotEntry,
)

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.data.constants import MCP_FILENAME
from agentbox.core.db import (
    AgentDefManager,
    AgentPromptResourceBindingManager,
    AgentVersionManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceFileResourceBindingManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceManager,
    WorkspaceRuntimePermissionManager,
    WorkspaceSubagentManager,
)
from agentbox.core.workspaces.generation import MaterializeOutcome
from agentbox.core.workspaces.generation.builders.from_db import load_workenv
from agentbox.core.engines.backends.recipe_loader import (
    list_recipes,
    load_recipe,
)
from agentbox.core.workspaces.construct import workspace_constructor
from agentbox.core.workspaces.generation.workspace_files import (
    materialize_workspace_files,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workspace resource resolution
# ---------------------------------------------------------------------------


def resolve_workspace_resources(
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    workspace_id: str,
) -> list[dict]:
    """Hydrate all active workspace file bindings into materializer-ready dicts."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return []

    bindings = workspace_file_resource_bindings.list_for_workspace(workspace_id)
    if not bindings:
        return []

    resolved: list[dict] = []
    for b in bindings:
        resource = resources.get_resource(b["resource_id"])
        if not resource:
            logger.warning(
                "workspace prep: workspace binding %s references missing resource %s — skipping",
                b["id"],
                b["resource_id"],
            )
            continue
        version_id = b.get("pinned_version_id")
        if not version_id:
            active = resource_versions.get_active_version(b["resource_id"])
            if not active:
                logger.warning(
                    "workspace prep: resource %s has no active version — skipping workspace binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = active["id"]
        version = resource_versions.get_version(version_id)
        if version is None:
            logger.warning(
                "workspace prep: version %s not found — skipping workspace binding %s",
                version_id,
                b["id"],
            )
            continue
        blobs = list(resource_blobs.iter_blobs(version_id))
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


def resolve_workspace_subagents(
    workspace_subagents: WorkspaceSubagentManager,
    agent_versions: AgentVersionManager,
    agent_defs: AgentDefManager,
    workspace_id: str,
) -> list[dict]:
    """Hydrate workspace subagent rows into renderer-ready dicts."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return []

    rows = workspace_subagents.list_for_workspace(workspace_id)
    if not rows:
        return []

    resolved: list[dict] = []
    for r in rows:
        agent_id = r["agent_id"]
        active = agent_versions.get_active(agent_id)
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
        agent_def = agent_defs.get(agent_id)
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
    workspace_env_doc_versions: WorkspaceEnvDocVersionManager,
    workspace_id: str,
    workdir: Path,
) -> list[EnvDocRenderEntry]:
    """Render the active env doc into CLAUDE.md and AGENTS.md in ``workdir``."""
    if not workspace_id or workspace_id == "<ephemeral>":
        return []

    doc = workspace_env_doc_versions.get_active(workspace_id)
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

    body = ""
    if isinstance(content_json, dict):
        body = content_json.get("body") or content_json.get("content") or ""
    if not isinstance(body, str):
        body = str(body)

    # The env-doc body is plain text; each engine's recipe ``context`` layout
    # names the instruction file it reads (claude → CLAUDE.md,
    # opencode → AGENTS.md). The workdir is engine-agnostic, so write the
    # same body to every engine's context file.
    filenames: set[str] = set()
    for engine in list_recipes():
        try:
            recipe = load_recipe(engine)
        except Exception:
            continue
        filename = recipe.resolve_layout("context")
        if filename:
            filenames.add(filename)

    snapshot_entries: list[EnvDocRenderEntry] = []
    for filename in sorted(filenames):
        dest = workdir / filename
        dest.write_text(body, encoding="utf-8")
        snapshot_entries.append(
            {
                "role": "env_doc",
                "file": filename,
                "workspace_id": workspace_id,
                "env_doc_version_id": doc["id"],
                "bytes": len(body.encode()),
            }
        )
    return snapshot_entries


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def workspace_outcomes_to_snapshot(outcomes: list[MaterializeOutcome]) -> list[WorkspaceFileSnapshotEntry]:
    """Convert MaterializeOutcome list to JSON-serializable snapshot entries."""
    entries: list[WorkspaceFileSnapshotEntry] = []
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


def prompt_resolution_to_snapshot(resolution: Any) -> list[PromptEmbedSnapshotEntry]:
    """Convert PromptResolution snapshot list to JSON-serializable entries."""
    entries: list[PromptEmbedSnapshotEntry] = []
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


def resolve_agent_prompt_bindings(
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    agent_id: str,
) -> list[dict]:
    """Hydrate all active prompt bindings for an agent into resolver-ready dicts.

    Returns the same shape as ``_resolve_binding_for_prompt`` in the API
    route, so ``resolve_prompt`` can consume them directly.
    """
    bindings = agent_prompt_resource_bindings.list_for_agent(agent_id)
    if not bindings:
        return []

    resolved: list[dict] = []
    for b in bindings:
        resource = resources.get_resource(b["resource_id"])
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
            active = resource_versions.get_active_version(b["resource_id"])
            if not active:
                logger.warning(
                    "workspace prep: resource %s has no active version — skipping prompt binding %s",
                    resource["slug"],
                    b["id"],
                )
                continue
            version_id = str(active["id"])
        version = resource_versions.get_version(version_id)
        if version is None:
            continue
        blobs = list(resource_blobs.iter_blobs(version_id))
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
    workspace_runtime_permissions: WorkspaceRuntimePermissionManager | None = None,
) -> dict:
    """Resolve effective workspace permissions from the DB overlay.

    ``workspace_runtime_permissions`` is the single source of truth for
    built-in tools, file scopes, max_tokens, and network/write flags.
    Workspaces with no overlay row receive an empty permissions dict —
    callers downstream treat that as "no constraints declared".
    """
    if not agent.workspace or agent.workspace == "<ephemeral>":
        return {}
    if workspace_runtime_permissions is None:
        return {}
    try:
        overlay = workspace_runtime_permissions.get_for_workspace(agent.workspace)
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
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    workspace_env_doc_versions: WorkspaceEnvDocVersionManager,
    workspace_runtime_permissions: WorkspaceRuntimePermissionManager | None = None,
    workspaces: WorkspaceManager,
    agent_defs: AgentDefManager,
    workspace_subagents: WorkspaceSubagentManager,
    agent_versions: AgentVersionManager,
    workspace_mcp_overrides: WorkspaceMcpOverrideManager,
    workspace_mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    settings: Settings,
    workspace_id: str | None,
    agent: AgentDef,
    workdir: Path,
    mcp_registry: Any = None,
    system_prompt: str | None = None,
) -> tuple[Path, list[RunSnapshotEntry]]:
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

    resource_snapshot_entries: list[RunSnapshotEntry] = []

    # One constructor drives both disk-writers across every engine recipe:
    # resource bindings into the persistent workdir, native config into run_dir.
    constructor = workspace_constructor()

    # ── 1. Workspace resources, env-doc, subagents ────────────────────────
    if workspace_id and workspace_id != "<ephemeral>":
        try:
            ws_bindings = resolve_workspace_resources(
                workspace_file_resource_bindings,
                resources,
                resource_versions,
                resource_blobs,
                workspace_id,
            )
            if ws_bindings:
                outcomes = constructor.materialize(
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
            env_doc_entries = render_env_doc(workspace_env_doc_versions, workspace_id, workdir)
            resource_snapshot_entries.extend(env_doc_entries)
        except Exception:
            logger.exception(
                "prepare_run_workdir: env doc rendering failed for workspace %r",
                workspace_id,
            )

        # Subagents are rendered natively into the run dir by the engine
        # recipes (step 3 render()), which is the run's cwd — no separate
        # workdir materialization needed.

    # ── 2. Create fresh run_dir ───────────────────────────────────────────
    run_dir = settings.runs_tmpfs_dir / uuid.uuid4().hex
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)

    # ── 3. Render native per-engine config into the run dir ───────────────
    # One WorkenvConfig, rendered through every engine recipe (Claude →
    # CLAUDE.md/.mcp.json/.claude/agents, OpenCode → AGENTS.md/opencode.json).
    # Tool gating is enforced by the backend at dispatch (--allowedTools),
    # not by a settings file, so permissions are left off the config here.
    permissions = load_workspace_permissions(workdir, agent, settings, workspace_runtime_permissions)
    wsid = workspace_id if workspace_id and workspace_id != "<ephemeral>" else agent.id
    config = load_workenv(
        workspaces,
        agent_defs,
        workspace_subagents,
        agent_versions,
        workspace_file_resource_bindings,
        workspace_mcp_overrides,
        workspace_mcp_tool_overrides,
        workspace_env_doc_versions,
        wsid,
        settings=settings,
        permissions=None,
    )
    constructor.generate(run_dir, config, system_prompt=system_prompt)

    # Claude runs with `--mcp-config .mcp.json --strict-mcp-config`, which
    # errors if the file is absent; render only emits it when servers exist.
    # ponytail: guarantee an empty one so a server-less run still launches.
    mcp_json = run_dir / MCP_FILENAME
    if not mcp_json.exists():
        mcp_json.write_text('{\n  "mcpServers": {}\n}\n', encoding="utf-8")

    files = permissions.get("files") or []
    if files:
        materialize_workspace_files(run_dir, files, settings.project_root)

    return run_dir, resource_snapshot_entries


# ---------------------------------------------------------------------------
# Per-run secrets injection
# ---------------------------------------------------------------------------


def write_secrets(
    workdir: Path,
    secrets: dict,
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
