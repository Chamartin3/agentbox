"""Inspect / manipulate a single repo-resource — read, update, publish, export, validate."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from agentbox.api.deps import get_resource_service
from agentbox.core.data.rows import RepoResourceRow, ResourceVersionRow
from agentbox.core.data.payload_types import (
    RenderedResourceResult,
    ResourceDetailResult,
    ResourceTreeResult,
    ResourceVersionsResult,
    ScriptSampleValidationResult,
)
from agentbox.core.service.resources import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
    ResourceService,
)
from agentbox.api.resources.repo._models import (
    PublishBody,
    RollbackBody,
    UpdateResourceBody,
    ValidateBody,
    _raise_not_found,
)

inspect_router = APIRouter(prefix="/api/repo-resources", tags=["repo-resources"])


@inspect_router.get("/{resource_id}")
def get_resource(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> ResourceDetailResult:
    try:
        return svc.get_resource(resource_id)
    except ResourceNotFound:
        _raise_not_found()


@inspect_router.patch("/{resource_id}")
def update_resource(
    resource_id: str,
    body: UpdateResourceBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> RepoResourceRow | None:
    try:
        return svc.update_resource(
            resource_id,
            display_name=body.display_name,
            description=body.description,
            tags=body.tags,
        )
    except ResourceNotFound:
        _raise_not_found()


@inspect_router.get("/{resource_id}/versions")
def list_versions(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> ResourceVersionsResult:
    try:
        return svc.list_versions(resource_id)
    except ResourceNotFound:
        _raise_not_found()


@inspect_router.post("/{resource_id}/versions/{version_id}/publish")
def publish_version(
    resource_id: str,
    version_id: str,
    body: PublishBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> ResourceVersionRow | None:
    try:
        return svc.publish_version(
            resource_id,
            version_id,
            reason=body.reason,
            actor=body.actor,
        )
    except ResourceNotFound:
        _raise_not_found("version not found")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@inspect_router.post("/{resource_id}/rollback")
def rollback_resource(
    resource_id: str,
    body: RollbackBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> ResourceVersionRow | None:
    try:
        return svc.rollback_resource(
            resource_id,
            target_version=body.target_version,
            reason=body.reason,
            actor=body.actor,
        )
    except ResourceNotFound:
        _raise_not_found()
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@inspect_router.get("/{resource_id}/blobs")
def get_blob(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    path: str = "",
    version_id: str | None = None,
) -> Response:
    try:
        blob = svc.get_blob(resource_id, path=path, version_id=version_id)
    except ResourceNotFound as exc:
        _raise_not_found(str(exc))
    except NoActiveVersion:
        _raise_not_found("no active version")
    return Response(
        content=blob["content"],
        media_type=blob.get("mime_type") or "application/octet-stream",
    )


@inspect_router.get("/{resource_id}/render")
def render_resource(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    version_id: str | None = None,
) -> RenderedResourceResult:
    try:
        return svc.render_resource(resource_id, version_id=version_id)
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")


@inspect_router.get("/{resource_id}/tree")
def get_tree(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    version_id: str | None = None,
) -> ResourceTreeResult:
    try:
        return svc.get_tree(resource_id, version_id=version_id)
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")


@inspect_router.get("/{resource_id}/export/pydantic")
def export_pydantic(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    class_name: str = "Model",
    version_id: str | None = None,
) -> Response:
    try:
        code = svc.export_pydantic(resource_id, class_name=class_name, version_id=version_id)
    except ResourceNotFound as exc:
        _raise_not_found(str(exc))
    except NoActiveVersion:
        _raise_not_found("no active version")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(content=code, media_type="text/x-python")


@inspect_router.post("/{resource_id}/validate")
def validate_script_sample(
    resource_id: str,
    body: ValidateBody,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
) -> ScriptSampleValidationResult:
    try:
        return svc.validate_script_sample(
            resource_id,
            sample=body.sample,
            direction=body.direction,
        )
    except ResourceNotFound:
        _raise_not_found()
    except NoActiveVersion:
        _raise_not_found("no active version")
    except InvalidResource as exc:
        raise HTTPException(400, str(exc)) from exc


@inspect_router.get("/{resource_id}/export/zip")
def export_zip(
    resource_id: str,
    svc: Annotated[ResourceService, Depends(get_resource_service)],
    version_id: str | None = None,
) -> Response:
    try:
        content, filename = svc.export_zip(resource_id, version_id=version_id)
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
