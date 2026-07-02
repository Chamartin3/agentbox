"""Workspace administration service — MCP overrides, host env, env docs, usage.

Pass-through functions that delegate to ``WorkspaceService``. UI layers call
these instead of reaching into the DB directly.

The ``store`` parameter has been removed — all workspace methods go through
``WorkspaceService`` (which owns its own DB managers). Agent-version methods
take the specific manager they need.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.data import EnvDocRow
from agentbox.core.service.resources.service import ResourceService
from agentbox.core.service.system.service import SystemService
from agentbox.core.service.workspaces.service import WorkspaceService

if TYPE_CHECKING:
    from agentbox.core.db import AgentMetaManager, AgentVersionManager
    from agentbox.core.data.rows import AgentMetaRow


def _ws() -> WorkspaceService:
    return WorkspaceService()


# ── Workspace registry ──────────────────────────────────────────────────


def get_workspace(name: str) -> dict | None:
    return _ws().get_workspace(name)


# ── Workspace MCP policy ────────────────────────────────────────────────


def get_workspace_mcp_policy(workspace_id: str) -> str:
    return _ws().get_mcp_policy(workspace_id)


def set_workspace_mcp_policy(workspace_id: str, policy: str) -> str:
    return _ws().set_mcp_policy(workspace_id, policy)


# ── Workspace MCP server overrides ──────────────────────────────────────


def list_workspace_mcp_server_overrides(workspace_id: str) -> list[dict]:
    return _ws().list_mcp_server_overrides(workspace_id)


def set_workspace_mcp_server_override(
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


def list_workspace_mcp_tool_overrides(workspace_id: str) -> list[dict]:
    return _ws().list_mcp_tool_overrides(workspace_id)


# ── Workspace file bindings ─────────────────────────────────────────────


def list_workspace_file_bindings(workspace_id: str) -> list[dict]:
    return ResourceService()._file_bindings.list_for_workspace(workspace_id)


def replace_workspace_file_bindings(
    workspace_id: str,
    bindings: list,
    *,
    reason: str,
    actor: str | None = None,
) -> list[dict]:
    return ResourceService()._file_bindings.replace_for_workspace(
        workspace_id, bindings, reason=reason, actor=actor
    )


# ── Host env profiles ───────────────────────────────────────────────────


def list_host_env_profiles() -> list[dict]:
    return _ws().list_host_env_profiles()


def get_workspace_host_env(workspace_id: str) -> dict | None:
    return _ws().get_workspace_host_env(workspace_id)


def resolve_workspace_host_env(workspace_id: str) -> dict:
    return _ws().resolve_workspace_host_env(workspace_id)


def list_host_env_calls_for_run(run_id: str) -> list[dict]:
    return SystemService().list_host_env_calls_for_run(run_id)


# ── Env docs ────────────────────────────────────────────────────────────


def get_active_env_doc(workspace_id: str) -> EnvDocRow | None:
    return _ws().get_active_env_doc(workspace_id)


def list_env_doc_versions(workspace_id: str) -> list[dict]:
    return _ws().list_env_doc_versions(workspace_id)


def save_env_doc(
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


def publish_env_doc(workspace_id: str, version_id: str) -> dict:
    return _ws().publish_env_doc(workspace_id, version_id)


def rollback_env_doc(
    workspace_id: str,
    version_id: str,
    *,
    changelog: str,
    actor: str | None = None,
) -> dict:
    return _ws().rollback_env_doc(
        workspace_id, version_id, changelog=changelog, actor=actor
    )


# ── Agent versions ──────────────────────────────────────────────────────


def replace_version_config(
    agent_versions: AgentVersionManager, version_id: int, config_json: str
) -> None:
    agent_versions.patch(version_id, config_json=config_json)


def update_agent_meta(
    agent_meta: AgentMetaManager,
    agent_id: str,
    *,
    sync_mode: str | None = None,
    export_to_disk: bool | None = None,
    source_path: str | None = None,
    source_format: str | None = None,
) -> AgentMetaRow | None:
    kwargs: dict = {}
    if sync_mode is not None:
        kwargs["sync_mode"] = sync_mode
    if export_to_disk is not None:
        kwargs["export_to_disk"] = 1 if export_to_disk else 0
    if source_path is not None:
        kwargs["source_path"] = source_path
    if source_format is not None:
        kwargs["source_format"] = source_format
    if kwargs:
        agent_meta.patch(agent_id, **kwargs)
    return agent_meta.get_meta(agent_id)
