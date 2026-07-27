"""Workspace MCP provisioning routes.

MCP server setup and tool toggles are **provisioning / scope** controls,
not authorization.  They express *what is installed and visible* in the
workspace — the agent's ``tool_grants`` endpoint is the sole
authorization surface.  Enable/disable here means “shown vs hidden”,
never “allowed vs forbidden”.
"""

from __future__ import annotations

import logging

from agentbox.core.data.payload_types import McpDiscoveryRefreshResult, ResolvedWorkspaceMcp
from agentbox.core.mcp.registry import McpRegistry

from typing import Annotated, TypedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_workspace_service
from agentbox.core.config import load_settings
from agentbox.core.data.constants import McpPolicy
from agentbox.core.data.rows import WorkspaceMcpOverrideRow, WorkspaceMcpToolOverrideRow
from agentbox.core.service.workspaces import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace-mcp-provisioning"])


class ServerOverrideBody(BaseModel):
    enabled: bool
    config_overrides: dict | None = None
    reason: str = Field(..., min_length=3)
    actor: str | None = None


class ToolOverrideBody(BaseModel):
    enabled: bool
    actor: str | None = None


class PolicyBody(BaseModel):
    default_policy: McpPolicy


class McpPolicyResult(TypedDict):
    """Response for MCP policy endpoints."""

    policy: McpPolicy


class DeleteOverrideResult(TypedDict):
    """Response for DELETE of a workspace MCP server override."""

    deleted: str
    removed: bool


@router.get("/api/workspaces/{workspace_id}/mcp")
def get_effective_mcp(
    workspace_id: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> ResolvedWorkspaceMcp:
    return ws.resolve_workspace_mcp_view(workspace_id)


@router.get("/api/workspaces/{workspace_id}/mcp/servers")
def get_effective_servers(
    workspace_id: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> ResolvedWorkspaceMcp:
    """Effective per-workspace MCP servers — union of manifest + overrides."""
    return ws.resolve_workspace_mcp_view(workspace_id)


@router.get("/api/workspaces/{workspace_id}/mcp/policy")
def get_policy(
    workspace_id: str, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]
) -> McpPolicyResult:
    return {"policy": ws.get_mcp_policy(workspace_id)}


@router.put("/api/workspaces/{workspace_id}/mcp/policy")
def set_policy(
    workspace_id: str,
    body: PolicyBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> McpPolicyResult:
    try:
        return {
            "policy": ws.set_mcp_policy(workspace_id, body.default_policy)
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/workspaces/{workspace_id}/mcp/servers/{server_name}")
async def set_server_override(
    workspace_id: str,
    server_name: str,
    body: ServerOverrideBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceMcpOverrideRow:
    try:
        result = ws.set_mcp_server_override(
            workspace_id,
            server_name,
            enabled=body.enabled,
            config_overrides=body.config_overrides,
            changelog=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Trigger discovery when a server is enabled and its cache is stale/absent.
    # Respects the existing cache TTL — skips re-discovery if cache is fresh.
    if body.enabled:
        registry = McpRegistry(load_settings().mcp_cache_dir)
        if not registry.is_cache_fresh(server_name):
            try:
                await ws.sync_mcp_discovery(workspace_id)
            except Exception:
                # Discovery errors are logged and suppressed — the override
                # was persisted successfully regardless.
                logger.warning(
                    "MCP discovery on attach failed for workspace=%r server=%r",
                    workspace_id,
                    server_name,
                    exc_info=True,
                )

    return result


@router.delete("/api/workspaces/{workspace_id}/mcp/servers/{server_name}")
def delete_server_override(
    workspace_id: str,
    server_name: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> DeleteOverrideResult:
    """Remove a workspace MCP override. Deletes a workspace-only server
    outright; clears the override for an inherited server."""
    removed = ws.delete_mcp_server_override(workspace_id, server_name)
    return {"deleted": server_name, "removed": removed}


@router.put(
    "/api/workspaces/{workspace_id}/mcp/servers/{server_name}/tools/{tool_name}"
)
def set_tool_override(
    workspace_id: str,
    server_name: str,
    tool_name: str,
    body: ToolOverrideBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceMcpToolOverrideRow:
    return ws.set_mcp_tool_override(
        workspace_id,
        server_name,
        tool_name,
        enabled=body.enabled,
        actor=body.actor,
    )


@router.post("/api/workspaces/{workspace_id}/mcp/refresh", status_code=200)
async def refresh_workspace_mcp_discovery(
    workspace_id: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> McpDiscoveryRefreshResult:
    """Connect to this workspace's enabled MCP servers and (re)populate the
    tool discovery cache. Returns the total tool count discovered."""
    return await ws.sync_mcp_discovery(workspace_id)
