"""/repo-resources endpoints — central resource repository.

Thin HTTP layer: handlers parse the request, delegate to
``core.service.resources``, and translate domain errors to
``HTTPException``. UploadFile reads stay here because they own the
HTTP-streaming boundary.
"""

from __future__ import annotations

from typing import Annotated, Literal, Never

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agentbox.api.deps import get_store
from agentbox.core.constants import ResourceType
from agentbox.core.service import SessionStore
from agentbox.core.service import resources as resources_service
from agentbox.core.service.resources import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
)

router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])


def _raise_not_found(detail: str = "resource not found") -> Never:
    raise HTTPException(status_code=404, detail=detail)


# --- request models ---


class CreateResourceBody(BaseModel):
    slug: str
    type: ResourceType
    display_name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class UpdateResourceBody(BaseModel):
    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class HostPathImportBody(BaseModel):
    path: str
    recursive: bool = True
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    changelog: str = Field(..., min_length=3)
    draft: bool = False
    actor: str | None = None


class PublishBody(BaseModel):
    reason: str = Field(..., min_length=3)
    actor: str | None = None


class RollbackBody(BaseModel):
    target_version: int
    reason: str = Field(..., min_length=3)
    actor: str | None = None


# --- endpoints ---


@router.get("")
def list_resources(
    store: Annotated[SessionStore, Depends(get_store)],
    type: ResourceType | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    return resources_service.list_resources(
        store=store,
        type=type,
        query=q,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201)
def create_resource(
    body: CreateResourceBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.create_resource(
            store=store,
            slug=body.slug,
            type=body.type,
            display_name=body.display_name,
            description=body.description,
            tags=body.tags,
        )
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{resource_id}")
def get_resource(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.get_resource(resource_id, store=store)
    except ResourceNotFound:
        _raise_not_found()


@router.patch("/{resource_id}")
def update_resource(
    resource_id: str,
    body: UpdateResourceBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.update_resource(
            resource_id,
            store=store,
            display_name=body.display_name,
            description=body.description,
            tags=body.tags,
        )
    except ResourceNotFound:
        _raise_not_found()


@router.get("/{resource_id}/versions")
def list_versions(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.list_versions(resource_id, store=store)
    except ResourceNotFound:
        _raise_not_found()


@router.post("/{resource_id}/versions/upload", status_code=201)
async def upload_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
):
    content = await file.read()
    try:
        return resources_service.import_upload_version(
            resource_id,
            store=store,
            filename=file.filename or "upload.bin",
            content=content,
            mime_type=file.content_type,
            changelog=changelog,
            draft=draft,
            actor=actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{resource_id}/versions/from-host-path", status_code=201)
def host_path_version(
    resource_id: str,
    body: HostPathImportBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.import_host_path_version(
            resource_id,
            store=store,
            path=body.path,
            include=body.include,
            exclude=body.exclude,
            changelog=body.changelog,
            draft=body.draft,
            actor=body.actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{resource_id}/versions/{version_id}/publish")
def publish_version(
    resource_id: str,
    version_id: str,
    body: PublishBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.publish_version(
            resource_id,
            version_id,
            store=store,
            reason=body.reason,
            actor=body.actor,
        )
    except ResourceNotFound:
        _raise_not_found("version not found")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{resource_id}/rollback")
def rollback_resource(
    resource_id: str,
    body: RollbackBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.rollback_resource(
            resource_id,
            store=store,
            target_version=body.target_version,
            reason=body.reason,
            actor=body.actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{resource_id}/blobs")
def get_blob(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    path: str = "",
    version_id: str | None = None,
):
    try:
        blob = resources_service.get_blob(
            resource_id, store=store, path=path, version_id=version_id
        )
    except ResourceNotFound as exc:
        _raise_not_found(str(exc))
    except NoActiveVersion:
        _raise_not_found("no active version")
    return Response(
        content=blob["content"],
        media_type=blob.get("mime_type") or "application/octet-stream",
    )


@router.get("/{resource_id}/render")
def render_resource(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    version_id: str | None = None,
):
    try:
        return resources_service.render_resource(
            resource_id, store=store, version_id=version_id
        )
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")


@router.get("/{resource_id}/tree")
def get_tree(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    version_id: str | None = None,
):
    try:
        return resources_service.get_tree(
            resource_id, store=store, version_id=version_id
        )
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")


@router.post("/{resource_id}/versions/upload-zip", status_code=201)
async def upload_zip_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
):
    content = await file.read()
    try:
        return resources_service.import_zip_version(
            resource_id,
            store=store,
            filename=file.filename or "upload.zip",
            content=content,
            changelog=changelog,
            draft=draft,
            actor=actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{resource_id}/versions/upload-schema", status_code=201)
async def upload_schema_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
):
    content = await file.read()
    try:
        return resources_service.import_schema_version(
            resource_id,
            store=store,
            filename=file.filename or "schema.json",
            content=content,
            changelog=changelog,
            draft=draft,
            actor=actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{resource_id}/versions/upload-script", status_code=201)
async def upload_script_version(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    language: str | None = None,
    input_schema_resource_id: str | None = None,
    output_schema_resource_id: str | None = None,
    draft: bool = False,
    actor: str | None = None,
):
    content = await file.read()
    try:
        return resources_service.import_script_version(
            resource_id,
            store=store,
            filename=file.filename or "script",
            content=content,
            changelog=changelog,
            language=language,
            input_schema_resource_id=input_schema_resource_id,
            output_schema_resource_id=output_schema_resource_id,
            draft=draft,
            actor=actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{resource_id}/export/pydantic")
def export_pydantic(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    class_name: str = "Model",
    version_id: str | None = None,
):
    try:
        code = resources_service.export_pydantic(
            resource_id,
            store=store,
            class_name=class_name,
            version_id=version_id,
        )
    except ResourceNotFound as exc:
        _raise_not_found(str(exc))
    except NoActiveVersion:
        _raise_not_found("no active version")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(content=code, media_type="text/x-python")


class ValidateBody(BaseModel):
    sample: dict | list | str | int | float | bool | None
    direction: Literal["input", "output"] = "input"


@router.post("/{resource_id}/validate")
def validate_script_sample(
    resource_id: str,
    body: ValidateBody,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.validate_script_sample(
            resource_id,
            store=store,
            sample=body.sample,
            direction=body.direction,
        )
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{resource_id}/export/zip")
def export_zip(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    version_id: str | None = None,
):
    try:
        content, filename = resources_service.export_zip(
            resource_id, store=store, version_id=version_id
        )
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{resource_id}", status_code=204)
def soft_delete_resource(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    reason: Annotated[str, Query(min_length=3)],
):
    try:
        resources_service.soft_delete_resource(resource_id, store=store, reason=reason)
    except ResourceNotFound:
        _raise_not_found()
    return Response(status_code=204)
