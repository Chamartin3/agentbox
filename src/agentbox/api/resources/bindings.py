"""Agent + workspace resource binding routes (Plans 02 + 03).

Thin HTTP layer: parses requests, delegates to ResourceService, maps domain errors.
Workspace mutations trigger ``WorkspaceService.build_workspace`` as a best-effort
side-effect after the binding write so the service stays transport-agnostic.
"""

from __future__ import annotations

import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentbox.api.deps import get_agent_service, get_resource_service, get_workspace_service
from agentbox.core.data.constants import MaterializeMode, OnConflict, PromptMode, PromptSlot
from agentbox.core.data.payload_types import (
    MaterializeDryRunResult,
    PromptBindingItemsResult,
    PromptBindingSpec,
    PromptPreviewResult,
    PromptResourcesResult,
    ResourcePreviewModesResult,
    SkillBindingsResult,
    WorkspaceBindingItemsResult,
    WorkspaceBindingSpec,
    WorkspaceResourcesResult,
)
from agentbox.core.service.resources.service import (
    AgentVersionMissing,
    BindingError,
    ResourceNotFound,
    ResourceService,
)
from agentbox.core.service.workspaces import WorkspaceService
from agentbox.core.service import AgentService, PreviewError

router = APIRouter(tags=["resource-bindings"])


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
    materialize_mode: MaterializeMode = MaterializeMode.COPY
    on_conflict: OnConflict = OnConflict.ERROR
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


# --- prompt bindings ---


def _prompt_spec(b: PromptBindingIn) -> PromptBindingSpec:
    return {
        "resource_id": b.resource_id,
        "marker": b.marker,
        "mode": b.mode,
        "slot": b.slot,
        "attach_as_reference": b.attach_as_reference,
        "pinned_version_id": b.pinned_version_id,
        "required": b.required,
        "display_order": b.display_order,
    }


def _workspace_spec(b: WorkspaceBindingIn) -> WorkspaceBindingSpec:
    return {
        "resource_id": b.resource_id,
        "target_path": b.target_path,
        "materialize_mode": b.materialize_mode,
        "on_conflict": b.on_conflict,
        "pinned_version_id": b.pinned_version_id,
        "display_order": b.display_order,
    }


@router.get("/api/agents/{agent_id}/prompt-resources")
def list_prompt_resources(
    agent_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> PromptResourcesResult:
    return svc.list_prompt_resources(agent_id)


@router.put("/api/agents/{agent_id}/prompt-resources")
def replace_prompt_resources(
    agent_id: str,
    body: ReplacePromptBindings,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> PromptBindingItemsResult:
    try:
        return svc.replace_prompt_resources(
            agent_id,
            [_prompt_spec(b) for b in body.bindings],
            reason=body.reason,
            actor=body.actor,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/agents/{agent_id}/prompt-resources/preview")
def preview_prompt(
    agent_id: str,
    body: PreviewPromptBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> PromptPreviewResult:
    override = (
        [_prompt_spec(b) for b in body.bindings] if body.bindings is not None else None
    )
    try:
        return svc.preview_prompt(
            agent_id,
            template=body.template,
            bindings_override=override,
        )
    except AgentVersionMissing as exc:
        raise HTTPException(404, str(exc)) from exc
    except PreviewError as exc:
        raise HTTPException(400, exc.detail) from exc


# --- workspace file bindings ---


@router.get("/api/workspaces/{workspace_id}/resources")
def list_workspace_resources(
    workspace_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> WorkspaceResourcesResult:
    return svc.list_workspace_resources(workspace_id)


@router.put("/api/workspaces/{workspace_id}/resources")
def replace_workspace_resources(
    workspace_id: str,
    body: ReplaceWorkspaceBindings,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceBindingItemsResult:
    try:
        result = svc.replace_workspace_resources(
            workspace_id,
            [_workspace_spec(b) for b in body.bindings],
            reason=body.reason,
            actor=body.actor,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Trigger workspace build as a best-effort side effect
    with contextlib.suppress(Exception):
        ws.build_workspace(workspace_id)
    return result


@router.post("/api/workspaces/{workspace_id}/resources/dry-run")
def dry_run_workspace_resources(
    workspace_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> MaterializeDryRunResult:
    return svc.dry_run_workspace_resources(workspace_id)


# --- preview rendering (no bindings, just a single resource preview) ---


@router.get("/api/repo-resources/{resource_id}/preview-modes")
def preview_modes(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> ResourcePreviewModesResult:
    try:
        return svc.preview_modes(resource_id)
    except ResourceNotFound as exc:
        raise HTTPException(404, "resource not found") from exc


# --- workspace subagents ---


@router.get("/api/workspaces/{workspace_id}/subagents")
def list_workspace_subagents(
    workspace_id: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    agent_svc: Annotated[AgentService, Depends(get_agent_service)],
) -> dict:
    # Enrichment with agent info is done here at the API layer
    items = svc.list_workspace_subagents_raw(workspace_id)
    enriched = []
    for s in items:
        agent = agent_svc.get_agent_def(s["agent_id"])
        enriched.append(
            {
                **s,
                "agent_name": getattr(agent, "name", None) if agent else None,
                "agent_description": getattr(agent, "description", None) if agent else None,
            }
        )
    return {"items": enriched}


@router.put("/api/workspaces/{workspace_id}/subagents")
def replace_workspace_subagents(
    workspace_id: str,
    body: ReplaceSubagents,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict:
    try:
        items = svc.replace_workspace_subagents(
            workspace_id,
            [{"agent_id": sub.agent_id, "alias": sub.alias, "display_order": sub.display_order} for sub in body.subagents],
            actor=body.actor,
        )
    except (ValueError, BindingError) as exc:
        raise HTTPException(400, str(exc)) from exc
    # Trigger workspace build as a best-effort side effect
    with contextlib.suppress(Exception):
        svc.build_workspace(workspace_id)
    return {"items": items}


# --- workspace skill bindings ---


@router.get("/api/workspaces/{workspace_id}/skill-bindings")
def list_workspace_skill_bindings(
    workspace_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> SkillBindingsResult:
    return svc.list_workspace_skill_bindings(workspace_id)


@router.put("/api/workspaces/{workspace_id}/skill-bindings")
def replace_workspace_skill_bindings(
    workspace_id: str,
    body: ReplaceSkillBindings,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    ws: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceBindingItemsResult:
    try:
        result = svc.replace_workspace_skill_bindings(
            workspace_id,
            body.skill_resource_ids,
            reason=body.reason,
            actor=body.actor,
        )
    except BindingError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Trigger workspace build as a best-effort side effect
    with contextlib.suppress(Exception):
        ws.build_workspace(workspace_id)
    return result
