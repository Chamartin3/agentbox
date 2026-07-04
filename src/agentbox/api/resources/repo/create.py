"""Create repo-resource endpoints — POST for resource + version creation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile

from agentbox.api.deps import get_resource_service
from agentbox.core.service.resources.service import InvalidResource, ResourceNotFound, ResourceService
from agentbox.api.resources.repo._models import (
    CreateResourceBody,
    HostPathImportBody,
    _raise_not_found,
)

create_router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])


@create_router.post("", status_code=201)
def create_resource(
    body: CreateResourceBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> dict:
    try:
        return svc.create_resource(
            slug=body.slug,
            type=body.type,
            display_name=body.display_name,
            description=body.description,
            tags=body.tags,
        )
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@create_router.post("/{resource_id}/versions/upload", status_code=201)
async def upload_version(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
) -> dict | None:
    content = await file.read()
    try:
        return svc.import_upload_version(
            resource_id,
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


@create_router.post("/{resource_id}/versions/from-host-path", status_code=201)
def host_path_version(
    resource_id: str,
    body: HostPathImportBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> dict | None:
    try:
        return svc.import_host_path_version(
            resource_id,
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


@create_router.post("/{resource_id}/versions/upload-zip", status_code=201)
async def upload_zip_version(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
) -> dict | None:
    content = await file.read()
    try:
        return svc.import_zip_version(
            resource_id,
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


@create_router.post("/{resource_id}/versions/upload-schema", status_code=201)
async def upload_schema_version(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    draft: bool = False,
    actor: str | None = None,
) -> dict | None:
    content = await file.read()
    try:
        return svc.import_schema_version(
            resource_id,
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


@create_router.post("/{resource_id}/versions/upload-script", status_code=201)
async def upload_script_version(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    file: UploadFile,
    changelog: Annotated[str, Query(min_length=3)],
    language: str | None = None,
    input_schema_resource_id: str | None = None,
    output_schema_resource_id: str | None = None,
    draft: bool = False,
    actor: str | None = None,
) -> dict | None:
    content = await file.read()
    try:
        return svc.import_script_version(
            resource_id,
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
