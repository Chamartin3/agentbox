"""Workspace administration service — MCP overrides, host env, env docs, usage.

Pass-through functions that delegate to ``WorkspaceService``. UI layers call
these instead of reaching into ``SessionStore`` directly. 

The ``store`` parameter is retained for backward compatibility but
ignored for workspace methods (which now go through ``WorkspaceService``).
Non-workspace methods (agent versions) still use ``store``.
"""

from __future__ import annotations

from agentbox.core.db import EnvDocRow, SessionStore, WorkspaceRow
from agentbox.core.service.system.service import SystemService
from agentbox.core.service.workspaces.service import WorkspaceService


def _ws() -> WorkspaceService:
    return WorkspaceService()


# ── Workspace registry ──────────────────────────────────────────────────


def get_workspace(store: SessionStore, name: str) -> WorkspaceRow | None:
    return store.get_workspace(name)


# ── Workspace MCP policy ────────────────────────────────────────────────


def get_workspace_mcp_policy(store: SessionStore, workspace_id: str) -> str:
    return _ws().get_mcp_policy(workspace_id)


def set_workspace_mcp_policy(
    store: SessionStore, workspace_id: str, policy: str
) -> str:
    return _ws().set_mcp_policy(workspace_id, policy)


# ── Workspace MCP server overrides ──────────────────────────────────────


def list_workspace_mcp_server_overrides(
    store: SessionStore, workspace_id: str
) -> list[dict]:
    return _ws().list_mcp_server_overrides(workspace_id)


def set_workspace_mcp_server_override(
    store: SessionStore,
    workspace_id: str,
    server_name: str,
    *,
    enabled: bool,
    changelog: str = "set via service",
    actor: str | None = None,
) -> dict:
    return _ws().set_mcp_server_override(
        workspace_id,
        server_name,
        enabled=enabled,
        changelog=changelog,
        actor=actor,
    )


# ── Workspace MCP tool overrides ────────────────────────────────────────


def list_workspace_mcp_tool_overrides(
    store: SessionStore, workspace_id: str
) -> list[dict]:
    return _ws().list_mcp_tool_overrides(workspace_id)


# ── Workspace file bindings ─────────────────────────────────────────────
# Note: file bindings are part of ResourceService (Plan 090). These remain
# on SessionStore until ResourceService exposes a manager-level interface.


def list_workspace_file_bindings(
    store: SessionStore, workspace_id: str
) -> list[dict]:
    from agentbox.core.service.resources.service import ResourceService
    return ResourceService()._file_bindings.list_for_workspace(workspace_id)


def replace_workspace_file_bindings(
    store: SessionStore,
    workspace_id: str,
    bindings: list,
    *,
    reason: str,
    actor: str | None = None,
) -> list[dict]:
    from agentbox.core.service.resources.service import ResourceService
    return ResourceService()._file_bindings.replace_for_workspace(
        workspace_id, bindings, reason=reason, actor=actor
    )


# ── Host env profiles ───────────────────────────────────────────────────


def list_host_env_profiles(store: SessionStore) -> list[dict]:
    return _ws().list_host_env_profiles()


def get_workspace_host_env(
    store: SessionStore, workspace_id: str
) -> dict | None:
    return _ws().get_workspace_host_env(workspace_id)


def resolve_workspace_host_env(
    store: SessionStore, workspace_id: str
) -> dict:
    return _ws().resolve_workspace_host_env(workspace_id)


def list_host_env_calls_for_run(
    store: SessionStore, run_id: str
) -> list[dict]:
    return SystemService().list_host_env_calls_for_run(run_id)


# ── Env docs ────────────────────────────────────────────────────────────


def get_active_env_doc(store: SessionStore, workspace_id: str) -> dict | None:
    return _ws().get_active_env_doc(workspace_id)


def list_env_doc_versions(store: SessionStore, workspace_id: str) -> list[dict]:
    return _ws().list_env_doc_versions(workspace_id)


def save_env_doc(
    store: SessionStore,
    workspace_id: str,
    content: dict,
    *,
    changelog: str,
    publish: bool = True,
    actor: str | None = None,
) -> dict:
    return _ws().save_env_doc(
        workspace_id, content, changelog=changelog, publish=publish, actor=actor
    )


def publish_env_doc(
    store: SessionStore, workspace_id: str, version_id: str
) -> dict:
    return _ws().publish_env_doc(workspace_id, version_id)


def rollback_env_doc(
    store: SessionStore,
    workspace_id: str,
    version_id: str,
    *,
    changelog: str,
    actor: str | None = None,
) -> dict:
    return _ws().rollback_env_doc(
        workspace_id, version_id, changelog=changelog, actor=actor
    )


# ── Agent versions (not workspace-specific — remain on SessionStore) ────


def replace_version_config(
    store: SessionStore, version_id: int, config_json: str
) -> None:
    store.replace_version_config(version_id, config_json)


def update_agent_meta(
    store: SessionStore,
    agent_id: str,
    *,
    sync_mode: str | None = None,
    export_to_disk: bool | None = None,
    source_path: str | None = None,
    source_format: str | None = None,
) -> dict | None:
    return store.update_agent_meta(
        agent_id,
        sync_mode=sync_mode,
        export_to_disk=export_to_disk,
        source_path=source_path,
        source_format=source_format,
    )
