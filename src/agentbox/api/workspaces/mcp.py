"""Workspace MCP provisioning routes.

MCP server setup and tool toggles are **provisioning / scope** controls,
not authorization.  They express *what is installed and visible* in the
workspace — the agent's ``tool_grants`` endpoint is the sole
authorization surface.  Enable/disable here means “shown vs hidden”,
never “allowed vs forbidden”.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_workspace_service
from agentbox.core.constants import McpPolicy
from agentbox.core.data.rows import WorkspaceMcpOverrideRow, WorkspaceMcpToolOverrideRow
from agentbox.core.service.workspaces.service import WorkspaceService

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


@router.get("/api/workspaces/{workspace_id}/mcp")
def get_effective_mcp(
    workspace_id: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    return ws.resolve_workspace_mcp(workspace_id)


@router.get("/api/workspaces/{workspace_id}/mcp/servers")
def get_effective_servers(
    workspace_id: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    """Effective per-workspace MCP servers — union of manifest + overrides."""
    return ws.resolve_workspace_mcp(workspace_id)


@router.get("/api/workspaces/{workspace_id}/mcp/policy")
def get_policy(
    workspace_id: str, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]
) -> dict:
    return {"policy": ws.get_mcp_policy(workspace_id)}


@router.put("/api/workspaces/{workspace_id}/mcp/policy")
def set_policy(
    workspace_id: str,
    body: PolicyBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    try:
        return {
            "policy": ws.set_mcp_policy(workspace_id, body.default_policy)
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/workspaces/{workspace_id}/mcp/servers/{server_name}")
def set_server_override(
    workspace_id: str,
    server_name: str,
    body: ServerOverrideBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceMcpOverrideRow:
    try:
        return ws.set_mcp_server_override(
            workspace_id,
            server_name,
            enabled=body.enabled,
            config_overrides=body.config_overrides,
            changelog=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def refresh_workspace_mcp_discovery(
    workspace_id: str,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    """Invalidate the MCP tool discovery cache for this workspace's servers.

    Returns count of cache entries removed.
    """
    return ws.refresh_mcp_discovery(workspace_id)
