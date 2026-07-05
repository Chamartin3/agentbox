"""REST endpoints for per-agent tool grant management.

Grants are validated against the workspace's installed catalog when a
``workspace_id`` is supplied.  Unbacked grants (tool not in the catalog)
are allowed but flagged with a warning — an agent may be configured
before its workspace finishes provisioning.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_agent_service, get_mcp_registry, get_resource_service, get_workspace_service
from agentbox.core.service import AgentService
from agentbox.core.service.workspaces.service import WorkspaceService
from agentbox.core.mcp.client.registry import McpRegistry

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
    svc: WorkspaceService,
    mcp_registry: McpRegistry,
) -> set[str]:
    """Return the set of tool/resource names installed in *workspace_id*."""
    names: set[str] = set()

    for t in svc.mcp_callables(workspace_id, mcp_registry):
        names.add(t.name)
    for t in svc.host_env_callables(workspace_id):
        names.add(t.name)

    # Resource bindings are included but only by resource_id / target_path.
    rsvc = get_resource_service()
    for b in rsvc.list_workspace_resources(workspace_id).get("items", []):
        names.add(b["target_path"] or b["resource_id"])

    return names


@router.get("/{agent_id}/tool_grants")
def list_grants(
    agent_id: str,
    include_revoked: bool = False,
    svc: AgentService = Depends(get_agent_service),
) -> dict:
    return {"items": svc.list_tool_grants(agent_id, include_revoked=include_revoked)}


@router.post("/{agent_id}/tool_grants", status_code=201)
def grant_tool(
    agent_id: str,
    body: GrantBody,
    ws_svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    mcp_registry: Annotated[McpRegistry, Depends(get_mcp_registry)],
    svc: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        result = svc.grant_tool(
            agent_id=agent_id,
            tool_name=body.tool_name,
            changelog=body.changelog,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Validate against workspace catalog (warn, not hard-fail).
    response: dict = dict(result)
    if body.workspace_id:
        installed = _catalog_tool_names(body.workspace_id, ws_svc, mcp_registry)
        if body.tool_name not in installed:
            response["warning"] = (
                f"Tool '{body.tool_name}' is not currently installed in "
                f"workspace '{body.workspace_id}' — grant is unbacked."
            )

    return response


@router.delete("/{agent_id}/tool_grants/{tool_name}", status_code=204)
def revoke_tool(
    agent_id: str,
    tool_name: str,
    body: RevokeBody,
    svc: AgentService = Depends(get_agent_service),
) -> None:
    try:
        svc.revoke_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=body.changelog,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
