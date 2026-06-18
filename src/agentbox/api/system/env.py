"""Workspace environment-instruction doc routes (Plan 04)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_settings, get_store
from agentbox.core.service import SessionStore
from agentbox.core.service import env_doc as svc

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
def get_env_doc(workspace_id: str, store: Annotated[SessionStore, Depends(get_store)]):
    active = store.get_active_env_doc(workspace_id)
    if not active:
        return {"active": None}
    return {"active": active}


@router.put("/api/workspaces/{workspace_id}/env-doc")
def save_env_doc(
    workspace_id: str,
    body: SaveEnvDocBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    """Save and publish the workspace env-doc, then re-sync on-disk renders."""
    try:
        return svc.save_and_sync_env_doc(
            store,
            get_settings(),
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
    store: Annotated[SessionStore, Depends(get_store)],
):
    if body.content is not None:
        content: object = body.content
    else:
        active = store.get_active_env_doc(workspace_id)
        if not active:
            raise HTTPException(status_code=404, detail="no env doc for workspace")
        content = active["content_json"]
    return svc.render_env_doc_preview(content)
