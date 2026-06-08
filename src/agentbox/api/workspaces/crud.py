"""/workspaces endpoints — inspect, create, reset, read/write files,
generate configs, permissions, skills.

Thin HTTP layer: handlers parse requests, delegate to
``core.service.workspaces``, and translate domain errors to
``HTTPException``. Pagination envelope wrapping stays at this layer
since it's a presentation concern.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agentbox.api._pagination import paginate_list
from agentbox.api.deps import get_loader, get_mcp_registry, get_settings, get_store
from agentbox.core.service import workspaces as workspaces_service
from agentbox.core.service.prompts import AgentNotFound
from agentbox.core.service.workspaces.errors import (
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _try_get_mcp_manifest():
    try:
        return get_mcp_registry().manifest
    except Exception:
        return None


def _raise_not_found(name: str) -> NoReturn:
    raise HTTPException(404, f"unknown workspace {name!r}")


def _raise_agent_not_found(agent_id: str) -> NoReturn:
    raise HTTPException(404, f"unknown agent {agent_id!r}")


def _build_workspace_cb(store, settings, name: str) -> None:
    from agentbox.core.workspaces.build import build_workspace_by_name

    build_workspace_by_name(store, settings, name)


# ---------------------------------------------------------------------------
# List / create / delete (registry)
# ---------------------------------------------------------------------------


@router.get("")
def list_workspaces(
    paginated: bool = False,
    q: str | None = None,
    sort: str | None = None,
    order: str = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict] | dict:
    result = workspaces_service.list_workspaces_enriched(
        store=get_store(), settings=get_settings(), loader=get_loader()
    )
    if paginated:
        return paginate_list(
            result,
            q=q,
            q_fields=("name", "description", "path"),
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
    return result


class CreateWorkspaceBody(BaseModel):
    name: str
    description: str | None = None
    path: str | None = None


@router.post("", status_code=201)
def create_workspace_registry(body: CreateWorkspaceBody) -> dict:
    try:
        return workspaces_service.create_workspace_registry(
            body.name,
            store=get_store(),
            description=body.description,
            path=body.path,
        )
    except WorkspaceExists as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/by-name/{name}", status_code=200)
def delete_workspace_registry(name: str, purge_disk: bool = False) -> dict:
    try:
        return workspaces_service.delete_workspace_registry(
            name,
            store=get_store(),
            settings=get_settings(),
            purge_disk=purge_disk,
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


# ---------------------------------------------------------------------------
# Workspace by name
# ---------------------------------------------------------------------------


@router.get("/by-name/{name}")
def get_workspace_by_name(name: str) -> dict:
    try:
        return workspaces_service.get_workspace_by_name(
            name, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@router.get("/by-name/{name}/permissions")
def get_permissions_by_name(name: str) -> dict:
    try:
        return workspaces_service.get_permissions(
            name,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
            mcp_manifest=_try_get_mcp_manifest(),
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


class PermissionsBody(BaseModel):
    permissions: dict


@router.put("/by-name/{name}/permissions")
def set_permissions_by_name(name: str, body: PermissionsBody) -> dict:
    try:
        return workspaces_service.set_permissions(
            name,
            body.permissions,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
            mcp_manifest=_try_get_mcp_manifest(),
            sync_cb=_build_workspace_cb,
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.get("/by-name/{name}/mcp-tools")
def get_workspace_mcp_tools(name: str) -> dict:
    try:
        return workspaces_service.get_workspace_mcp_tools(
            name,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
            mcp_manifest=_try_get_mcp_manifest(),
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


# ---------------------------------------------------------------------------
# Config / skills generation
# ---------------------------------------------------------------------------


@router.post("/by-name/{name}/generate-configs")
def generate_configs_by_name(name: str) -> dict:
    try:
        return workspaces_service.generate_configs_by_name(
            name,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
            mcp_manifest=_try_get_mcp_manifest(),
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.post("/by-name/{name}/generate-skills")
def generate_skills_by_name(name: str) -> dict:
    try:
        return workspaces_service.generate_skills_by_name(
            name, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.get("/by-name/{name}/skills")
def list_skills_by_name(name: str) -> dict:
    try:
        return workspaces_service.list_skills_by_name(
            name, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.get("/by-name/{name}/skills/{skill_name}")
def get_skill_content_by_name(name: str, skill_name: str) -> dict:
    try:
        payload = workspaces_service.get_skill_content_by_name(
            name,
            skill_name,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
        )
    except WorkspaceNotFound:
        _raise_not_found(name)
    if payload is None:
        raise HTTPException(404, f"skill {skill_name!r} not found")
    return payload


# ---------------------------------------------------------------------------
# Files by workspace name
# ---------------------------------------------------------------------------


class FileBody(BaseModel):
    path: str
    content: str


@router.get("/by-name/{name}/file")
def read_file_by_name(name: str, path: str) -> dict:
    try:
        payload = workspaces_service.read_file_by_name(
            name, path, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except WorkspaceNotFound:
        _raise_not_found(name)
    except WorkspacePathEscape as exc:
        raise HTTPException(400, "path escapes workspace") from exc
    if payload is None:
        raise HTTPException(404, "no such file")
    return payload


@router.put("/by-name/{name}/file")
def write_file_by_name(name: str, body: FileBody) -> dict:
    try:
        return workspaces_service.write_file_by_name(
            name,
            body.path,
            body.content,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
        )
    except WorkspaceNotFound:
        _raise_not_found(name)
    except WorkspacePathEscape as exc:
        raise HTTPException(400, "path escapes workspace") from exc


# ---------------------------------------------------------------------------
# Legacy agent-centric endpoints (kept for backward compat)
# ---------------------------------------------------------------------------


@router.get("/{agent_id}")
def get_workspace(agent_id: str) -> dict:
    try:
        return workspaces_service.get_workspace_for_agent(
            agent_id, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except AgentNotFound:
        _raise_agent_not_found(agent_id)


@router.post("/{agent_id}")
def create_workspace(agent_id: str) -> dict:
    try:
        return workspaces_service.create_workspace_for_agent(
            agent_id, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc


@router.delete("/{agent_id}")
def reset_workspace(agent_id: str) -> dict:
    try:
        return workspaces_service.reset_workspace_for_agent(
            agent_id, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc


@router.post("/{agent_id}/generate-configs")
def generate_configs(agent_id: str) -> dict:
    try:
        return workspaces_service.generate_configs_for_agent(
            agent_id,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
            mcp_manifest=_try_get_mcp_manifest(),
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{agent_id}/skills")
def list_skills(agent_id: str) -> dict:
    try:
        return workspaces_service.list_skills_for_agent(
            agent_id, store=get_store(), settings=get_settings(), loader=get_loader()
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{agent_id}/file")
def read_file(agent_id: str, path: str) -> dict:
    try:
        payload = workspaces_service.read_file_for_agent(
            agent_id,
            path,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc
    except WorkspacePathEscape as exc:
        raise HTTPException(400, "path escapes workspace") from exc
    if payload is None:
        raise HTTPException(404, "no such file")
    return payload


@router.put("/{agent_id}/file")
def write_file(agent_id: str, body: FileBody) -> dict:
    try:
        return workspaces_service.write_file_for_agent(
            agent_id,
            body.path,
            body.content,
            store=get_store(),
            settings=get_settings(),
            loader=get_loader(),
        )
    except AgentNotFound as exc:
        raise HTTPException(404) from exc
    except WorkspacePathEscape as exc:
        raise HTTPException(400, "path escapes workspace") from exc
