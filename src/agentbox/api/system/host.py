"""Host-env provisioning routes.

Host-environment capabilities are **provisioning**, not authorization.
They declare what host capabilities *exist* in a workspace (filesystem
access, shell execution, HTTP, etc.) and the scoping constraints
(paths, allowlists) on those capabilities.  The agent's ``tool_grants``
endpoint is the sole authorization surface; effective permissions are
``agent_authorizes ∩ host_env_exists ∩ host_env_scope``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_workspace_service
from agentbox.core.service import WorkspaceService
from agentbox.core.service.system.service import SystemService
from agentbox.core.tools import CAPABILITIES

router = APIRouter(tags=["host-env-provisioning"])


class ProfileBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    grants: dict
    actor: str | None = None


class WorkspaceHostEnvBody(BaseModel):
    """Provisioning payload: host-env capabilities available in a workspace.

    These declare what host capabilities *exist* and their scoping
    (paths, allowlists).  The agent's ``tool_grants`` is the sole
    authorization surface.
    """
    profile_id: str | None = None
    overrides: dict | None = None
    reason: str = Field(..., min_length=3)
    actor: str | None = None


@router.get("/api/host-env/capabilities")
def list_capabilities() -> dict:
    return {
        "capabilities": [
            {
                "name": c.name,
                "description": c.description,
                "grant_schema": c.grant_schema,
                "default_granted": c.default_granted,
            }
            for c in CAPABILITIES.values()
        ]
    }


@router.get("/api/host-env/profiles")
def list_profiles(ws: Annotated[WorkspaceService, Depends(get_workspace_service)]) -> dict:
    return {"items": ws.list_host_env_profiles()}


@router.post("/api/host-env/profiles", status_code=201)
def create_profile(
    body: ProfileBody, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]
) -> dict:
    return ws.upsert_host_env_profile(
        name=body.name,
        description=body.description,
        grants=body.grants,
        actor=body.actor,
    )


@router.put("/api/host-env/profiles/{profile_id}")
def update_profile(
    profile_id: str,
    body: ProfileBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    if not ws.get_host_env_profile(profile_id):
        raise HTTPException(status_code=404, detail="profile not found")
    return ws.upsert_host_env_profile(
        profile_id=profile_id,
        name=body.name,
        description=body.description,
        grants=body.grants,
        actor=body.actor,
    )


@router.delete("/api/host-env/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: str, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]) -> None:
    ws.delete_host_env_profile(profile_id)


@router.get("/api/workspaces/{workspace_id}/host-env")
def get_workspace_host_env(
    workspace_id: str, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]
) -> dict:
    """Read the host-env provisioning config for *workspace_id*."""
    return ws.resolve_workspace_host_env(workspace_id)


@router.put("/api/workspaces/{workspace_id}/host-env")
def set_workspace_host_env(
    workspace_id: str,
    body: WorkspaceHostEnvBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    try:
        ws.set_workspace_host_env(
            workspace_id,
            profile_id=body.profile_id,
            overrides=body.overrides,
            changelog=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ws.resolve_workspace_host_env(workspace_id)


@router.get("/api/runs/{run_id}/host-env-calls")
def list_run_calls(run_id: str) -> dict:
    return {"items": SystemService().list_host_env_calls_for_run(run_id)}
