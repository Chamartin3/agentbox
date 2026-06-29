"""Resource CRUD + version lifecycle service operations.

.. deprecated::
    These standalone functions are retained for backward compatibility
    with existing test code. New code should use ``ResourceService``
    directly from ``agentbox.core.service.resources.service``.
"""

from __future__ import annotations

from typing import cast

from agentbox.core.constants import ResourceType
from agentbox.core.db import RepoResourceRow, SessionStore
from agentbox.core.service.resources.service import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
    ResourceService,
)

__all__ = [
    "ResourceNotFound",
    "InvalidResource",
    "NoActiveVersion",
    "resolve_resource_id",
    "list_resources",
    "create_resource",
    "get_resource",
    "update_resource",
    "list_versions",
    "publish_version",
    "rollback_resource",
    "soft_delete_resource",
    "list_repo_resources",
    "get_repo_resource_by_slug",
    "create_repo_resource",
    "list_repo_versions",
    "import_repo_version",
    "publish_repo_version",
    "rollback_repo_resource",
    "list_prompt_bindings",
    "replace_prompt_bindings",
]


def _svc() -> ResourceService:
    return ResourceService()


def resolve_resource_id(store: SessionStore, id_or_slug: str) -> str | None:  # noqa: ARG001
    return _svc().resolve_resource_id(id_or_slug)


def _resolve_or_raise(store: SessionStore, id_or_slug: str) -> str:  # noqa: ARG001
    return _svc()._resolve_or_raise(id_or_slug)  # type: ignore[attr-defined]


def _active_version_or_raise(store: SessionStore, resource_id: str) -> dict:  # noqa: ARG001
    return _svc()._active_version_or_raise(resource_id)  # type: ignore[attr-defined]


def list_resources(
    *,
    store: SessionStore,  # noqa: ARG001
    type: ResourceType | None = None,
    query: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return _svc().list_resources(
        type=type, query=query, include_deleted=include_deleted,
        limit=limit, offset=offset,
    )


def create_resource(
    *,
    store: SessionStore,  # noqa: ARG001
    slug: str,
    type: ResourceType,
    display_name: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> RepoResourceRow:
    return cast(RepoResourceRow, _svc().create_resource(
        slug=slug, type=type, display_name=display_name,
        description=description, tags=tags,
    ))


def get_resource(resource_id: str, *, store: SessionStore) -> dict:  # noqa: ARG001
    return _svc().get_resource(resource_id)


def update_resource(resource_id: str, *, store: SessionStore, display_name: str | None = None, description: str | None = None, tags: list[str] | None = None) -> RepoResourceRow:  # noqa: ARG001
    return cast(RepoResourceRow, _svc().update_resource(
        resource_id,
        display_name=display_name, description=description, tags=tags,
    ))


def list_versions(resource_id: str, *, store: SessionStore) -> dict:  # noqa: ARG001
    return _svc().list_versions(resource_id)


def publish_version(resource_id: str, version_id: str, *, store: SessionStore, reason: str, actor: str | None = None) -> dict:  # noqa: ARG001
    return _svc().publish_version(resource_id, version_id, reason=reason, actor=actor)


def rollback_resource(resource_id: str, *, store: SessionStore, target_version: int, reason: str, actor: str | None = None) -> dict:  # noqa: ARG001
    return _svc().rollback_resource(resource_id, target_version=target_version, reason=reason, actor=actor)


def soft_delete_resource(resource_id: str, *, store: SessionStore, reason: str) -> None:  # noqa: ARG001
    _svc().soft_delete_resource(resource_id, reason=reason)


def _require_resource(store: SessionStore, resource_id: str) -> RepoResourceRow:  # noqa: ARG001
    return _svc()._require_resource(resource_id)  # type: ignore[attr-defined]


def list_repo_resources(store: SessionStore, *, type: str | None = None, limit: int = 50) -> list[dict]:  # noqa: ARG001
    return _svc().list_resources(type=cast("ResourceType | None", type), limit=limit)["items"]


def get_repo_resource_by_slug(store: SessionStore, slug: str) -> RepoResourceRow | None:  # noqa: ARG001
    result = _svc().get_by_slug(slug)
    return cast("RepoResourceRow | None", result)


def create_repo_resource(store: SessionStore, slug: str, type: str, display_name: str, *, description: str | None = None, tags: list[str] | None = None, created_by: str | None = None) -> RepoResourceRow:  # noqa: ARG001
    return cast(RepoResourceRow, _svc().create_resource(
        slug=slug, type=cast(ResourceType, type), display_name=display_name,
        description=description, tags=tags,
    ))


def list_repo_versions(store: SessionStore, resource_id: str) -> list[dict]:  # noqa: ARG001
    return _svc().list_versions(resource_id)["items"]


def import_repo_version(store: SessionStore, resource_id: str, blobs: list[tuple[str, bytes, str | None, str | None]], *, import_source: str, changelog: str, source_metadata: dict | None = None, metadata: dict | None = None, draft: bool = False, created_by: str | None = None, activate: bool = True) -> dict:  # noqa: ARG001
    # This legacy signature doesn't map cleanly to ResourceService's
    # import methods. Build a simple upload-like import.
    return _svc().import_upload_version(
        resource_id,
        filename="import",
        content=blobs[0][1] if blobs else b"",
        mime_type=blobs[0][2] if blobs else None,
        changelog=changelog,
        draft=draft,
        actor=created_by,
    )


def publish_repo_version(store: SessionStore, version_id: str, *, reason: str, activated_by: str | None = None) -> dict:  # noqa: ARG001
    # Need resource_id for publish. Get it from the version.
    svc = _svc()
    # publish_version requires (resource_id, version_id, reason, actor)
    # We don't have resource_id here. Use a workaround by looking up the version.
    v = svc._resource_versions.get_version(version_id)  # type: ignore[attr-defined]
    if v is None:
        raise ResourceNotFound(version_id)
    return svc.publish_version(v["resource_id"], version_id, reason=reason, actor=activated_by)


def rollback_repo_resource(store: SessionStore, resource_id: str, target_version: int, *, reason: str, activated_by: str | None = None) -> dict:  # noqa: ARG001
    return _svc().rollback_resource(resource_id, target_version=target_version, reason=reason, actor=activated_by)


def list_prompt_bindings(store: SessionStore, agent_id: str) -> list[dict]:  # noqa: ARG001
    return _svc().list_prompt_bindings_raw(agent_id)


def replace_prompt_bindings(store: SessionStore, agent_id: str, bindings: list[dict], *, reason: str, actor: str | None = None) -> list[dict]:  # noqa: ARG001
    return _svc().replace_prompt_bindings_raw(agent_id, bindings, reason=reason)
