"""Workspace MCP override routes (Plan 05).

Transport-only: parses bodies, calls
:mod:`agentbox.core.service.workspaces`, maps store ValueErrors to 400.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.service import SessionStore
from agentbox.core.service import workspaces as ws_service

router = APIRouter(tags=["workspace-mcp"])

Policy = Literal["allow_all_unless_disabled", "deny_all_unless_enabled"]


class ServerOverrideBody(BaseModel):
    enabled: bool
    config_overrides: dict | None = None
    reason: str = Field(..., min_length=3)
    actor: str | None = None


class ToolOverrideBody(BaseModel):
    enabled: bool
    actor: str | None = None


class PolicyBody(BaseModel):
    default_policy: Policy


@router.get("/api/workspaces/{workspace_id}/mcp")
def get_effective_mcp(
    workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]
):
    return ws_service.resolve_workspace_mcp(workspace_id, store=store)


@router.get("/api/workspaces/{workspace_id}/mcp/servers")
def get_effective_servers(
    workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]
):
    """Effective per-workspace MCP servers — union of manifest + overrides."""
    return ws_service.resolve_workspace_mcp(workspace_id, store=store)


@router.get("/api/workspaces/{workspace_id}/mcp/policy")
def get_policy(workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]):
    return {"policy": store.get_workspace_mcp_policy(workspace_id)}


@router.put("/api/workspaces/{workspace_id}/mcp/policy")
def set_policy(
    workspace_id: str,
    body: PolicyBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return {
            "policy": store.set_workspace_mcp_policy(workspace_id, body.default_policy)
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/workspaces/{workspace_id}/mcp/servers/{server_name}")
def set_server_override(
    workspace_id: str,
    server_name: str,
    body: ServerOverrideBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return store.set_workspace_mcp_server_override(
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
    store: Annotated[SessionStore, Depends(get_store)],
):
    return store.set_workspace_mcp_tool_override(
        workspace_id,
        server_name,
        tool_name,
        enabled=body.enabled,
        actor=body.actor,
    )


@router.post("/api/workspaces/{workspace_id}/mcp/refresh", status_code=200)
def refresh_workspace_mcp_discovery(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Invalidate the MCP tool discovery cache for this workspace's servers.

    Returns count of cache entries removed.
    """
    return ws_service.refresh_workspace_mcp_discovery(workspace_id, store=store)
