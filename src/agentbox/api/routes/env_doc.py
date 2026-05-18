"""Workspace environment-instruction doc routes (Plan 04)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentbox.api.deps import get_settings, get_store
from agentbox.core.data.store import SessionStore
from agentbox.core.workspace.env_doc.renderers import (
    AgentsMdRenderer,
    ClaudeMdRenderer,
    RuntimeContext,
)
from agentbox.core.workspace.env_doc.renderers.base import ReferenceEntry
from agentbox.core.workspace.env_doc.schema import EnvDocContent
from agentbox.core.workspace.sync import sync_workspace_by_name

router = APIRouter(tags=["env-doc"])


class SaveEnvDocBody(BaseModel):
    """Body for saving an env-doc. Drafts and changelog requirements were
    removed — every save is live and immediately syncs to disk.
    ``reason``/``actor`` are kept optional for audit but not required."""

    content: EnvDocContent
    reason: str = "edit"
    actor: str | None = None


class PreviewEnvDocBody(BaseModel):
    content: EnvDocContent | None = None


def _runtime_context(store: SessionStore, workspace_id: str) -> RuntimeContext:
    skills: list[ReferenceEntry] = []
    folders: list[ReferenceEntry] = []
    for b in store.list_workspace_file_bindings(workspace_id):
        resource = store.get_repo_resource(b["resource_id"])
        if not resource:
            continue
        entry = ReferenceEntry(label=resource["display_name"], detail=b.get("target_path") or "")
        if resource["type"] == "skill":
            skills.append(entry)
        elif resource["type"] == "folder":
            folders.append(entry)
    return RuntimeContext(skills=skills, folders=folders)


def _render_both(content: EnvDocContent, ctx: RuntimeContext) -> dict[str, str]:
    return {
        "claude_md": ClaudeMdRenderer().render(content, ctx),
        "agents_md": AgentsMdRenderer().render(content, ctx),
    }


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
    """Save and publish the workspace env-doc.

    Drafts were removed — every save is live, immediately becomes the
    active version, and triggers a workspace re-sync to refresh
    CLAUDE.md / AGENTS.md on disk.
    """
    try:
        result = store.save_env_doc(
            workspace_id,
            body.content.model_dump(),
            changelog=body.reason,
            publish=True,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        sync_workspace_by_name(store, get_settings(), workspace_id)
    except Exception:
        logging.getLogger(__name__).exception(
            "env_doc save: sync_workspace_by_name failed for %s", workspace_id
        )
    return result


@router.post("/api/workspaces/{workspace_id}/env-doc/preview")
def preview_env_doc(
    workspace_id: str,
    body: PreviewEnvDocBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    if body.content is not None:
        content = body.content
    else:
        active = store.get_active_env_doc(workspace_id)
        if not active:
            raise HTTPException(status_code=404, detail="no env doc for workspace")
        content = EnvDocContent.model_validate(active["content_json"])
    ctx = _runtime_context(store, workspace_id)
    return _render_both(content, ctx)


