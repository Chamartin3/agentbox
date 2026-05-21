"""Workspace MCP override routes (Plan 05)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.data.store import SessionStore

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


def _manifest_servers(store: SessionStore) -> list[dict]:
    """Best-effort: return manifest-declared MCP servers as list of dicts.

    Each entry has at minimum ``name`` and ``config``. The resolver does
    not require any other fields. If the manifest is not loaded, returns
    an empty list — callers see the "no manifest" case explicitly.
    """
    servers = store.get_project_mcp_servers()
    if not servers:
        return []
    return [{"name": s.name, "config": s.model_dump(exclude={"name"})} for s in servers]


@router.get("/api/workspaces/{workspace_id}/mcp")
def get_effective_mcp(
    workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]
):
    servers = _manifest_servers(store)
    return store.resolve_workspace_mcp(workspace_id, servers)


@router.get("/api/workspaces/{workspace_id}/mcp/servers")
def get_effective_servers(
    workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]
):
    """Effective per-workspace MCP servers — union of manifest + overrides."""
    servers = _manifest_servers(store)
    return store.resolve_workspace_mcp(workspace_id, servers)


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
    Returns count of cache entries removed."""
    resolved = store.resolve_workspace_mcp(workspace_id, _manifest_servers(store))
    removed = 0
    for s in resolved.get("servers", []):
        removed += store.invalidate_server_cache(s["name"])
    return {"invalidated": removed}
