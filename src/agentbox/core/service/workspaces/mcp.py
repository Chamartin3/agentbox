"""Workspace-level MCP server resolution and discovery refresh.

Delegates to ``WorkspaceService``.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import McpDiscoveryRefreshResult, ResolvedWorkspaceMcp

from agentbox.core.service.workspaces.service import WorkspaceService

__all__ = [
    "resolve_workspace_mcp",
    "refresh_workspace_mcp_discovery",
]


def _ws() -> WorkspaceService:
    return WorkspaceService()


def resolve_workspace_mcp(workspace_id: str) -> ResolvedWorkspaceMcp:
    return _ws().resolve_workspace_mcp(workspace_id)


def refresh_workspace_mcp_discovery(workspace_id: str) -> McpDiscoveryRefreshResult:
    return _ws().refresh_mcp_discovery(workspace_id)
