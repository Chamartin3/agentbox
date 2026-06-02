"""Host-env profile + workspace grant routes (Plan 06)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.data import SessionStore
from agentbox.core.tools import CAPABILITIES

router = APIRouter(tags=["host-env"])


class ProfileBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    grants: dict
    actor: str | None = None


class WorkspaceGrantBody(BaseModel):
    profile_id: str | None = None
    overrides: dict | None = None
    reason: str = Field(..., min_length=3)
    actor: str | None = None


@router.get("/api/host-env/capabilities")
def list_capabilities():
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
def list_profiles(store: Annotated[SessionStore, Depends(get_store)]):
    return {"items": store.list_host_env_profiles()}


@router.post("/api/host-env/profiles", status_code=201)
def create_profile(
    body: ProfileBody, store: Annotated[SessionStore, Depends(get_store)]
):
    return store.upsert_host_env_profile(
        name=body.name,
        description=body.description,
        grants=body.grants,
        actor=body.actor,
    )


@router.put("/api/host-env/profiles/{profile_id}")
def update_profile(
    profile_id: str,
    body: ProfileBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    if not store.get_host_env_profile(profile_id):
        raise HTTPException(status_code=404, detail="profile not found")
    return store.upsert_host_env_profile(
        profile_id=profile_id,
        name=body.name,
        description=body.description,
        grants=body.grants,
        actor=body.actor,
    )


@router.delete("/api/host-env/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: str, store: Annotated[SessionStore, Depends(get_store)]):
    store.delete_host_env_profile(profile_id)


@router.get("/api/workspaces/{workspace_id}/host-env")
def get_workspace_grants(
    workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]
):
    return store.resolve_workspace_host_env(workspace_id)


@router.put("/api/workspaces/{workspace_id}/host-env")
def set_workspace_grants(
    workspace_id: str,
    body: WorkspaceGrantBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        store.set_workspace_host_env(
            workspace_id,
            profile_id=body.profile_id,
            overrides=body.overrides,
            changelog=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.resolve_workspace_host_env(workspace_id)


@router.get("/api/runs/{run_id}/host-env-calls")
def list_run_calls(run_id: str, store: Annotated[SessionStore, Depends(get_store)]):
    return {"items": store.list_host_env_calls_for_run(run_id)}
