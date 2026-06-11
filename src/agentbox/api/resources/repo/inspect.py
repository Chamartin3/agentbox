"""Inspect / manipulate a single repo-resource — read, update, publish, export, validate."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from agentbox.api.deps import get_store
from agentbox.core.service import SessionStore
from agentbox.core.service import resources as resources_service
from agentbox.core.service.resources import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
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
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.get_resource(resource_id, store=store)
    except ResourceNotFound:
        _raise_not_found()


@inspect_router.patch("/{resource_id}")
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


@inspect_router.get("/{resource_id}/versions")
def list_versions(
    resource_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
):
    try:
        return resources_service.list_versions(resource_id, store=store)
    except ResourceNotFound:
        _raise_not_found()


@inspect_router.post("/{resource_id}/versions/{version_id}/publish")
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


@inspect_router.post("/{resource_id}/rollback")
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
        raise __import__("fastapi").HTTPException(400, str(exc)) from exc


@inspect_router.get("/{resource_id}/blobs")
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


@inspect_router.get("/{resource_id}/render")
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


@inspect_router.get("/{resource_id}/tree")
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


@inspect_router.get("/{resource_id}/export/pydantic")
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


@inspect_router.post("/{resource_id}/validate")
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


@inspect_router.get("/{resource_id}/export/zip")
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
        raise __import__("fastapi").HTTPException(400, str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
