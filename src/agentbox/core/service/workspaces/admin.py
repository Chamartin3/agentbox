"""Workspace administration free functions — MCP overrides, host env, env docs.

Thin pass-throughs to ``WorkspaceService`` for UI/facade callers. Relocated
from the former top-level ``core.service.workspace_admin`` bridge so each
helper lives in the domain that owns it.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import ResolvedHostEnv

from agentbox.core.data import EnvDocRow
from agentbox.core.data.rows import (
    HostEnvProfileRow,
    WorkspaceMcpOverrideRow,
    WorkspaceMcpToolOverrideRow,
    WorkspaceRow,
    WorkspaceHostEnvGrantRow,
)
from agentbox.core.service.workspaces.service import WorkspaceService


def _ws() -> WorkspaceService:
    return WorkspaceService()


# ── Workspace registry ──────────────────────────────────────────────────


def get_workspace(name: str) -> WorkspaceRow | None:
    return _ws().get_workspace(name)


# ── Workspace MCP policy ────────────────────────────────────────────────


def get_workspace_mcp_policy(workspace_id: str) -> str:
    return _ws().get_mcp_policy(workspace_id)


def set_workspace_mcp_policy(workspace_id: str, policy: str) -> str:
    return _ws().set_mcp_policy(workspace_id, policy)


# ── Workspace MCP server overrides ──────────────────────────────────────


def list_workspace_mcp_server_overrides(workspace_id: str) -> list[WorkspaceMcpOverrideRow]:
    return _ws().list_mcp_server_overrides(workspace_id)


def set_workspace_mcp_server_override(
    workspace_id: str,
    server_name: str,
    *,
    enabled: bool,
    changelog: str = "set via service",
    actor: str | None = None,
) -> WorkspaceMcpOverrideRow:
    return _ws().set_mcp_server_override(
        workspace_id,
        server_name,
        enabled=enabled,
        changelog=changelog,
        actor=actor,
    )


# ── Workspace MCP tool overrides ────────────────────────────────────────


def list_workspace_mcp_tool_overrides(workspace_id: str) -> list[WorkspaceMcpToolOverrideRow]:
    return _ws().list_mcp_tool_overrides(workspace_id)


# ── Host env profiles ───────────────────────────────────────────────────


def list_host_env_profiles() -> list[HostEnvProfileRow]:
    return _ws().list_host_env_profiles()


def get_workspace_host_env(workspace_id: str) -> WorkspaceHostEnvGrantRow | None:
    return _ws().get_workspace_host_env(workspace_id)


def resolve_workspace_host_env(workspace_id: str) -> ResolvedHostEnv:
    return _ws().resolve_workspace_host_env(workspace_id)


# ── Env docs ────────────────────────────────────────────────────────────


def get_active_env_doc(workspace_id: str) -> EnvDocRow | None:
    return _ws().get_active_env_doc(workspace_id)


def list_env_doc_versions(workspace_id: str) -> list[EnvDocRow]:
    return _ws().list_env_doc_versions(workspace_id)


def save_env_doc(
    workspace_id: str,
    content: dict,
    *,
    changelog: str,
    publish: bool = True,
    actor: str | None = None,
) -> EnvDocRow:
    return _ws().save_env_doc(
        workspace_id, content, changelog=changelog, publish=publish, actor=actor
    )


def publish_env_doc(workspace_id: str, version_id: str) -> EnvDocRow:
    return _ws().publish_env_doc(workspace_id, version_id)


def rollback_env_doc(
    workspace_id: str,
    version_id: str,
    *,
    changelog: str,
    actor: str | None = None,
) -> EnvDocRow:
    return _ws().rollback_env_doc(
        workspace_id, version_id, changelog=changelog, actor=actor
    )
