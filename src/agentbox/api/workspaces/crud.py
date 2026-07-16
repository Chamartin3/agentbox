"""/workspaces endpoints — inspect, create, reset, read/write files,
generate configs, permissions, skills.

Thin HTTP layer: handlers parse requests, delegate to
``core.service.workspaces``, and translate domain errors to
``HTTPException``. Pagination envelope wrapping stays at this layer
since it's a presentation concern.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import (
    GeneratedConfigsResult,
    GeneratedSkillsResult,
    PermissionsPatch,
    PermissionsSetResult,
    PermissionsView,
    SkillContentResult,
    SkillsListResult,
    WorkspaceDeleteResult,
    WorkspaceDetail,
    WorkspaceFileInfo,
    WorkspaceFileRead,
    WorkspaceFileWrite,
    WorkspaceListItem,
    WorkspaceMcpToolsResult,
)

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agentbox.api.schemas import PaginatedEnvelope, paginate_list
from agentbox.api.deps import get_mcp_registry, get_settings, get_workspace_service
from agentbox.core.config import Settings
from agentbox.core.data.rows import WorkspaceRow
from agentbox.core.service.workspaces import is_user_file
from agentbox.core.service.workspaces import WorkspaceService
from agentbox.core.data.errors import (
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)
router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _try_get_mcp_manifest() -> object | None:
    try:
        return get_mcp_registry().manifest
    except Exception:
        return None


def _raise_not_found(name: str) -> NoReturn:
    raise HTTPException(404, f"unknown workspace {name!r}")


def _build_workspace_cb(settings: Settings, name: str) -> None:
    """Callback to build workspace after permissions are set."""
    WorkspaceService().build_workspace(name)


# ---------------------------------------------------------------------------
# List / create / delete (registry)
# ---------------------------------------------------------------------------


@router.get("")
def list_workspaces(
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    paginated: bool = False,
    q: str | None = None,
    sort: str | None = None,
    order: str = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[WorkspaceListItem] | PaginatedEnvelope:
    result = svc.list_workspaces(settings=settings)
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
def create_workspace_registry(
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    body: CreateWorkspaceBody,
) -> WorkspaceRow:
    try:
        return svc.create_workspace(
            body.name,
            description=body.description,
            path=body.path,
        )
    except WorkspaceExists as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/by-name/{name}", status_code=200)
def delete_workspace_registry(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    purge_disk: bool = False,
) -> WorkspaceDeleteResult:
    try:
        return svc.delete_workspace(
            name,
            settings=settings,
            purge_disk=purge_disk,
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


# ---------------------------------------------------------------------------
# Workspace by name
# ---------------------------------------------------------------------------


@router.get("/by-name/{name}")
def get_workspace_by_name(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkspaceDetail:
    try:
        ws_path, _ = svc.resolve_workspace_path(name, settings=settings)
        files: list[WorkspaceFileInfo] = []
        if ws_path.exists():
            for p in sorted(ws_path.rglob("*")):
                if p.is_file():
                    rel = str(p.relative_to(ws_path))
                    if not is_user_file(rel):
                        continue
                    files.append({"path": rel, "size": p.stat().st_size})
        return {
            "name": name,
            "path": str(ws_path),
            "exists": ws_path.exists(),
            "files": files,
            "generated_configs": {},
        }
    except WorkspaceNotFound:
        _raise_not_found(name)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@router.get("/by-name/{name}/permissions")
def get_permissions_by_name(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> PermissionsView:
    try:
        return svc.get_permissions(name)
    except WorkspaceNotFound:
        _raise_not_found(name)


class PermissionsBody(BaseModel):
    permissions: PermissionsPatch


@router.put("/by-name/{name}/permissions")
def set_permissions_by_name(
    name: str,
    body: PermissionsBody,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PermissionsSetResult:
    try:
        return svc.set_permissions(
            name,
            body.permissions,
            settings=settings,
            sync_cb=_build_workspace_cb,
        )
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.get("/by-name/{name}/mcp-tools")
def get_workspace_mcp_tools(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceMcpToolsResult:
    try:
        return svc.get_workspace_mcp_tools(name)
    except WorkspaceNotFound:
        _raise_not_found(name)


# ---------------------------------------------------------------------------
# Config / skills generation
# ---------------------------------------------------------------------------


@router.post("/by-name/{name}/generate-configs")
def generate_configs_by_name(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GeneratedConfigsResult:
    try:
        return svc.generate_configs(name, settings=settings)
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.post("/by-name/{name}/generate-skills")
def generate_skills_by_name(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GeneratedSkillsResult:
    try:
        return svc.generate_skills(name, settings=settings)
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.get("/by-name/{name}/skills")
def list_skills_by_name(
    name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SkillsListResult:
    try:
        return svc.list_skills(name, settings=settings)
    except WorkspaceNotFound:
        _raise_not_found(name)


@router.get("/by-name/{name}/skills/{skill_name}")
def get_skill_content_by_name(
    name: str,
    skill_name: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SkillContentResult:
    try:
        payload = svc.get_skill_content(name, skill_name, settings=settings)
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
def read_file_by_name(
    name: str,
    path: str,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkspaceFileRead:
    try:
        payload = svc.read_workspace_file(name, path, settings=settings)
    except WorkspaceNotFound:
        _raise_not_found(name)
    except WorkspacePathEscape as exc:
        raise HTTPException(400, "path escapes workspace") from exc
    if payload is None:
        raise HTTPException(404, "no such file")
    return payload


@router.put("/by-name/{name}/file")
def write_file_by_name(
    name: str,
    body: FileBody,
    svc: Annotated[WorkspaceService, Depends(get_workspace_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkspaceFileWrite:
    try:
        return svc.write_workspace_file(
            name,
            body.path,
            body.content,
            settings=settings,
        )
    except WorkspaceNotFound:
        _raise_not_found(name)
    except WorkspacePathEscape as exc:
        raise HTTPException(400, "path escapes workspace") from exc
