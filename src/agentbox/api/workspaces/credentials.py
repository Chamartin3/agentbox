"""/api/workspaces/{workspace_id}/credentials — per-workspace enablement.

Shows the full inventory (available) plus which credential ids the workspace
has enabled. PUT replaces the enabled set. Enabled credentials are
materialized into a run's env when the workspace is built.
"""

from __future__ import annotations

from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.data.rows import CredentialInventoryEntry

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCredentialsResult(TypedDict):
    """Response envelope: the full inventory + this workspace's enabled ids."""

    available: list[CredentialInventoryEntry]
    enabled: list[str]


class SetBody(BaseModel):
    enabled: list[str] = Field(default_factory=list)


@router.get("/{workspace_id}/credentials")
def get_workspace_credentials(
    workspace_id: str,
    ctx: APIContext = Depends(get_api_context),
) -> WorkspaceCredentialsResult:
    return {
        "available": ctx.credentials.inventory(),
        "enabled": ctx.credentials.list_workspace_credentials(workspace_id),
    }


@router.put("/{workspace_id}/credentials")
def set_workspace_credentials(
    workspace_id: str,
    body: SetBody,
    ctx: APIContext = Depends(get_api_context),
) -> WorkspaceCredentialsResult:
    try:
        enabled = ctx.credentials.set_workspace_credentials(workspace_id, body.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"available": ctx.credentials.inventory(), "enabled": enabled}
