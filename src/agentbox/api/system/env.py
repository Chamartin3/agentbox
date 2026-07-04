"""Workspace environment-instruction doc routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentbox.api.context import APIContext
from agentbox.api.deps import get_api_context
from agentbox.core.service import render_env_doc_preview

router = APIRouter(tags=["env-doc"])


class SaveEnvDocBody(BaseModel):
    """Body for saving an env-doc. Every save is live and immediately syncs
    to disk. ``content`` is the raw markdown body."""

    content: str
    reason: str = "edit"
    actor: str | None = None


class PreviewEnvDocBody(BaseModel):
    content: str | None = None


@router.get("/api/workspaces/{workspace_id}/env-doc")
def get_env_doc(
    workspace_id: str,
    ctx: APIContext = Depends(get_api_context),
) -> dict:
    active = ctx.workspaces.get_active_env_doc(workspace_id)
    if not active:
        return {"active": None}
    return {"active": active}


@router.put("/api/workspaces/{workspace_id}/env-doc")
def save_env_doc(
    workspace_id: str,
    body: SaveEnvDocBody,
    ctx: APIContext = Depends(get_api_context),
) -> dict:
    """Save and publish the workspace env-doc, then re-sync on-disk renders."""
    try:
        return ctx.workspaces.save_and_sync_env_doc(
            workspace_id,
            content=body.content,
            reason=body.reason,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/workspaces/{workspace_id}/env-doc/preview")
def preview_env_doc(
    workspace_id: str,
    body: PreviewEnvDocBody,
    ctx: APIContext = Depends(get_api_context),
) -> dict:
    if body.content is not None:
        content: object = body.content
    else:
        active = ctx.workspaces.get_active_env_doc(workspace_id)
        if not active:
            raise HTTPException(status_code=404, detail="no env doc for workspace")
        content = active["content_json"]
    return render_env_doc_preview(content)
