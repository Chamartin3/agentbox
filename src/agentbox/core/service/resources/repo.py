"""Resource CRUD + version lifecycle service operations.

.. deprecated::
    These standalone functions are retained for backward compatibility
    with test code transitioning to ``ResourceService``. New code should
    use ``ResourceService`` directly from
    ``agentbox.core.service.resources.service``.
"""

from __future__ import annotations

from typing import cast

from agentbox.core.constants import ResourceType
from agentbox.core.data import RepoResourceRow
from agentbox.core.service.resources.service import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
    ResourceService,
)

__all__ = [
    "InvalidResource",
    "NoActiveVersion",
    "ResourceNotFound",
    "resolve_resource_id",
    "list_resources",
    "create_resource",
    "get_resource",
    "update_resource",
    "list_versions",
    "publish_version",
    "rollback_resource",
    "soft_delete_resource",
]


def _svc() -> ResourceService:
    return ResourceService()


def resolve_resource_id(id_or_slug: str) -> str | None:
    return _svc().resolve_resource_id(id_or_slug)


def list_resources(
    *,
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


def get_resource(resource_id: str) -> dict:
    return _svc().get_resource(resource_id)


def update_resource(resource_id: str, *, display_name: str | None = None, description: str | None = None, tags: list[str] | None = None) -> RepoResourceRow:
    return cast(RepoResourceRow, _svc().update_resource(
        resource_id,
        display_name=display_name, description=description, tags=tags,
    ))


def list_versions(resource_id: str) -> dict:
    return _svc().list_versions(resource_id)


def publish_version(resource_id: str, version_id: str, *, reason: str, actor: str | None = None) -> dict:
    return _svc().publish_version(resource_id, version_id, reason=reason, actor=actor)


def rollback_resource(resource_id: str, *, target_version: int, reason: str, actor: str | None = None) -> dict:
    return _svc().rollback_resource(resource_id, target_version=target_version, reason=reason, actor=actor)


def soft_delete_resource(resource_id: str, *, reason: str) -> None:
    _svc().soft_delete_resource(resource_id, reason=reason)
