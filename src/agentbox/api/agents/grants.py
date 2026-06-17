"""REST endpoints for per-agent tool grant management (Plan 19, 062_01).

Grants are validated against the workspace's installed catalog when a
``workspace_id`` is supplied.  Unbacked grants (tool not in the catalog)
are allowed but flagged with a warning — an agent may be configured
before its workspace finishes provisioning.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_mcp_registry, get_store
from agentbox.api.workspaces.catalog import _resolve_host_env_tools, _resolve_mcp_tools
from agentbox.core.service import SessionStore
from agentbox.core.workspaces.mcp.client.registry import McpRegistry

router = APIRouter(prefix="/api/agents", tags=["agent-tool-grants"])


class GrantBody(BaseModel):
    tool_name: str = Field(..., min_length=1)
    changelog: str = Field(..., min_length=3)
    actor: str | None = None
    workspace_id: str | None = None


class RevokeBody(BaseModel):
    changelog: str = Field(..., min_length=3)
    actor: str | None = None


def _catalog_tool_names(
    workspace_id: str,
    store: SessionStore,
    mcp_registry: McpRegistry,
) -> set[str]:
    """Return the set of tool/resource names installed in *workspace_id*."""
    names: set[str] = set()

    for t in _resolve_mcp_tools(workspace_id, store, mcp_registry):
        names.add(t["name"])
    for t in _resolve_host_env_tools(workspace_id, store):
        names.add(t["name"])

    # Resource bindings are included but only by resource_id / target_path.
    for b in store.list_workspace_file_bindings(workspace_id):
        names.add(b.get("target_path", b.get("resource_id", "")))

    return names


@router.get("/{agent_id}/tool_grants")
def list_grants(
    agent_id: str,
    include_revoked: bool = False,
    store: Annotated[SessionStore, Depends(get_store)] = ...,  # pyright: ignore[reportArgumentType]
):
    return {
        "items": store.list_agent_tool_grants(agent_id, include_revoked=include_revoked)
    }


@router.post("/{agent_id}/tool_grants", status_code=201)
def grant_tool(
    agent_id: str,
    body: GrantBody,
    store: Annotated[SessionStore, Depends(get_store)],
    mcp_registry: Annotated[McpRegistry, Depends(get_mcp_registry)],
):
    try:
        result = store.grant_agent_tool(
            agent_id=agent_id,
            tool_name=body.tool_name,
            changelog=body.changelog,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Validate against workspace catalog (warn, not hard-fail).
    if body.workspace_id:
        installed = _catalog_tool_names(body.workspace_id, store, mcp_registry)
        if body.tool_name not in installed:
            result["warning"] = (
                f"Tool '{body.tool_name}' is not currently installed in "
                f"workspace '{body.workspace_id}' — grant is unbacked."
            )

    return result


@router.delete("/{agent_id}/tool_grants/{tool_name}", status_code=204)
def revoke_tool(
    agent_id: str,
    tool_name: str,
    body: RevokeBody,
    store: Annotated[SessionStore, Depends(get_store)] = ...,  # pyright: ignore[reportArgumentType]
):
    try:
        store.revoke_agent_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=body.changelog,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
