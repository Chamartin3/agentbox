"""/api/workspaces/{workspace_id}/env-vars — per-workspace custom shell env vars.

GET returns the current ``{KEY: VALUE}`` mapping. PUT replaces the full
set atomically. These are injected into the agent subprocess at run time.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_workspace_service
from agentbox.core.service.workspaces import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class EnvVarsBody(BaseModel):
    vars: dict[str, str]


@router.get("/{workspace_id}/env-vars")
def get_workspace_env_vars(
    workspace_id: str,
    ws: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    return ws.get_env_vars(workspace_id)


@router.put("/{workspace_id}/env-vars")
def set_workspace_env_vars(
    workspace_id: str,
    body: EnvVarsBody,
    ws: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, str]:
    try:
        return ws.set_env_vars(workspace_id, body.vars)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
