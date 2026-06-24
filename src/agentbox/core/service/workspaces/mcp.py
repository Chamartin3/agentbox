"""Workspace-level MCP server resolution and discovery refresh."""

from __future__ import annotations

from agentbox.core.db import SessionStore
from agentbox.core.db.execution.snapshots import McpSnapshot
from agentbox.core.service.system.service import SystemService

__all__ = [
    "resolve_workspace_mcp",
    "refresh_workspace_mcp_discovery",
]


def _manifest_servers() -> list[dict]:
    """Project-manifest MCP servers projected as ``{name, config}`` dicts.

    Returns ``[]`` when no manifest is loaded — callers see the "no
    manifest" case explicitly rather than via an exception.
    """
    servers = SystemService().get_project_mcp_servers()
    if not servers:
        return []
    return [{"name": s.name, "config": s.model_dump(exclude={"name"})} for s in servers]


def resolve_workspace_mcp(workspace_id: str, *, store: SessionStore) -> McpSnapshot:
    """Effective per-workspace MCP servers — union of manifest + overrides."""
    return store.resolve_workspace_mcp(workspace_id, _manifest_servers())


def refresh_workspace_mcp_discovery(
    workspace_id: str, *, store: SessionStore
) -> dict:
    """Invalidate the MCP tool discovery cache for this workspace's servers.

    Returns ``{invalidated: N}`` — number of cache entries removed.
    """
    resolved = store.resolve_workspace_mcp(workspace_id, _manifest_servers())
    removed = 0
    for s in resolved.get("servers", []):
        removed += store.invalidate_server_cache(s["name"])
    return {"invalidated": removed}
