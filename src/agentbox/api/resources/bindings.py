"""Agent + workspace resource binding routes (Plans 02 + 03).

Thin HTTP layer: parses requests, delegates to
``core.service.bindings``, maps domain errors. Workspace mutations
inject ``sync_workspace_by_name`` as the sync callback so the
service stays transport-agnostic.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_settings, get_store
from agentbox.core.data import SessionStore
from agentbox.core.service import bindings as bindings_service
from agentbox.core.service.bindings import (
    AgentVersionMissing,
    BindingError,
    PreviewError,
)
from agentbox.core.service.resources import ResourceNotFound
from agentbox.core.workspace.sync import sync_workspace_by_name

router = APIRouter(tags=["resource-bindings"])

PromptMode = Literal["inline", "skill_primer", "name_only", "manifest"]
PromptSlot = Literal["system", "user_template", "input_schema", "output_schema"]
MaterializeMode = Literal["copy", "symlink", "mount"]
OnConflict = Literal["error", "overwrite", "skip"]


# --- request models ---


class PromptBindingIn(BaseModel):
    resource_id: str
    marker: str | None = None
    mode: PromptMode | None = None
    slot: PromptSlot | None = None
    attach_as_reference: bool = False
    pinned_version_id: str | None = None
    required: bool = True
    display_order: int = 0


class ReplacePromptBindings(BaseModel):
    bindings: list[PromptBindingIn]
    reason: str = Field(default="ui edit", min_length=1)
    actor: str | None = None


class SubagentIn(BaseModel):
    agent_id: str
    alias: str
    display_order: int = 0


class ReplaceSubagents(BaseModel):
    subagents: list[SubagentIn]
    actor: str | None = None


class WorkspaceBindingIn(BaseModel):
    resource_id: str
    target_path: str | None = None
    materialize_mode: MaterializeMode = "copy"
    on_conflict: OnConflict = "error"
    pinned_version_id: str | None = None
    display_order: int = 0


class ReplaceWorkspaceBindings(BaseModel):
    bindings: list[WorkspaceBindingIn]
    reason: str = Field(default="ui edit", min_length=1)
    actor: str | None = None


class PreviewPromptBody(BaseModel):
    template: str | None = None
    bindings: list[PromptBindingIn] | None = None


class ReplaceSkillBindings(BaseModel):
    skill_resource_ids: list[str] = Field(default_factory=list)
    reason: str = "skill bindings update"
    actor: str | None = None


# --- prompt bindings (Plan 02) ---


@router.get("/api/agents/{agent_id}/prompt-resources")
def list_prompt_resources(
    agent_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    return bindings_service.list_prompt_resources(agent_id, store=store)


@router.put("/api/agents/{agent_id}/prompt-resources")
def replace_prompt_resources(
    agent_id: str,
    body: ReplacePromptBindings,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return bindings_service.replace_prompt_resources(
            agent_id,
            [b.model_dump() for b in body.bindings],
            store=store,
            reason=body.reason,
            actor=body.actor,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/agents/{agent_id}/prompt-resources/preview")
def preview_prompt(
    agent_id: str,
    body: PreviewPromptBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    override = (
        [b.model_dump() for b in body.bindings] if body.bindings is not None else None
    )
    try:
        return bindings_service.preview_prompt(
            agent_id,
            store=store,
            template=body.template,
            bindings_override=override,
        )
    except AgentVersionMissing as exc:
        raise HTTPException(404, str(exc)) from exc
    except PreviewError as exc:
        raise HTTPException(400, exc.detail) from exc


# --- workspace file bindings (Plan 03) ---


@router.get("/api/workspaces/{workspace_id}/resources")
def list_workspace_resources(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    return bindings_service.list_workspace_resources(workspace_id, store=store)


@router.put("/api/workspaces/{workspace_id}/resources")
def replace_workspace_resources(
    workspace_id: str,
    body: ReplaceWorkspaceBindings,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return bindings_service.replace_workspace_resources(
            workspace_id,
            [b.model_dump() for b in body.bindings],
            store=store,
            reason=body.reason,
            actor=body.actor,
            settings=get_settings(),
            sync_cb=sync_workspace_by_name,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/workspaces/{workspace_id}/resources/dry-run")
def dry_run_workspace_resources(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    return bindings_service.dry_run_workspace_resources(workspace_id, store=store)


# --- preview rendering (no bindings, just a single resource preview) ---


@router.get("/api/repo-resources/{resource_id}/preview-modes")
def preview_modes(resource_id: str, store: Annotated[SessionStore, Depends(get_store)]):
    try:
        return bindings_service.preview_modes(resource_id, store=store)
    except ResourceNotFound as exc:
        raise HTTPException(404, "resource not found") from exc


# --- workspace subagents ---


@router.get("/api/workspaces/{workspace_id}/subagents")
def list_workspace_subagents(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    return bindings_service.list_workspace_subagents(workspace_id, store=store)


@router.put("/api/workspaces/{workspace_id}/subagents")
def replace_workspace_subagents(
    workspace_id: str,
    body: ReplaceSubagents,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return bindings_service.replace_workspace_subagents(
            workspace_id,
            [s.model_dump() for s in body.subagents],
            store=store,
            actor=body.actor,
            settings=get_settings(),
            sync_cb=sync_workspace_by_name,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc


# --- workspace skill bindings ---


@router.get("/api/workspaces/{workspace_id}/skill-bindings")
def list_workspace_skill_bindings(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    return bindings_service.list_workspace_skill_bindings(workspace_id, store=store)


@router.put("/api/workspaces/{workspace_id}/skill-bindings")
def replace_workspace_skill_bindings(
    workspace_id: str,
    body: ReplaceSkillBindings,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return bindings_service.replace_workspace_skill_bindings(
            workspace_id,
            body.skill_resource_ids,
            store=store,
            reason=body.reason,
            actor=body.actor,
            settings=get_settings(),
            sync_cb=sync_workspace_by_name,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc
