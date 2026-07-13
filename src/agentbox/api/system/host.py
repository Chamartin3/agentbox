"""Host-env provisioning routes.

Host-environment capabilities are **provisioning**, not authorization.
They declare what host capabilities *exist* in a workspace (filesystem
access, shell execution, HTTP, etc.) and the scoping constraints
(paths, allowlists) on those capabilities.  The agent's ``tool_grants``
endpoint is the sole authorization surface; effective permissions are
``agent_authorizes ∩ host_env_exists ∩ host_env_scope``.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from agentbox.core.data.payload_types import ResolvedHostEnv

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_workspace_service
from agentbox.core.data.rows import HostEnvProfileRow, HostEnvCallLogRow
from agentbox.core.service import WorkspaceService
from agentbox.core.service.system import SystemService
from agentbox.core.tools import CAPABILITIES

router = APIRouter(tags=["host-env-provisioning"])


class CapabilityEntry(TypedDict):
    """One entry in the capabilities list."""

    name: str
    description: str
    grant_schema: dict
    default_granted: bool


class ListCapabilitiesResult(TypedDict):
    """Response envelope for GET /api/host-env/capabilities."""

    capabilities: list[CapabilityEntry]


class ListProfilesResult(TypedDict):
    """Response envelope for GET /api/host-env/profiles."""

    items: list[HostEnvProfileRow]


class ListRunCallsResult(TypedDict):
    """Response envelope for GET /api/runs/{run_id}/host-env-calls."""

    items: list[HostEnvCallLogRow]


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
def list_capabilities() -> ListCapabilitiesResult:
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
def list_profiles(ws: Annotated[WorkspaceService, Depends(get_workspace_service)]) -> ListProfilesResult:
    return {"items": ws.list_host_env_profiles()}


@router.post("/api/host-env/profiles", status_code=201)
def create_profile(
    body: ProfileBody, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]
) -> HostEnvProfileRow:
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
) -> HostEnvProfileRow:
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


@router.get("/api/agents/{agent_id}/host-env")
def get_agent_host_env(
    agent_id: str, ws: Annotated[WorkspaceService, Depends(get_workspace_service)]
) -> ResolvedHostEnv:
    """Read the host-env grant config for *agent_id* (authorization = agent)."""
    return ws.resolve_agent_host_env(agent_id)


@router.put("/api/agents/{agent_id}/host-env")
def set_agent_host_env(
    agent_id: str,
    body: WorkspaceHostEnvBody,
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> ResolvedHostEnv:
    try:
        ws.set_agent_host_env(
            agent_id,
            profile_id=body.profile_id,
            overrides=body.overrides,
            changelog=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ws.resolve_agent_host_env(agent_id)


@router.get("/api/runs/{run_id}/host-env-calls")
def list_run_calls(run_id: str) -> ListRunCallsResult:
    return {"items": SystemService().list_host_env_calls_for_run(run_id)}
