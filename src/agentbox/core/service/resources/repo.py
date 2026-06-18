"""Resource CRUD + version lifecycle service operations."""

from __future__ import annotations

from typing import cast

from agentbox.core.constants import ResourceType
from agentbox.core.db import RepoResourceRow, SessionStore

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


class ResourceNotFound(LookupError):
    def __init__(self, resource_id: str) -> None:
        super().__init__(f"resource {resource_id!r} not found")
        self.resource_id = resource_id


class InvalidResource(ValueError):
    """Resource exists but the requested operation is invalid for it."""


class NoActiveVersion(LookupError):
    def __init__(self, resource_id: str) -> None:
        super().__init__(f"no active version for resource {resource_id!r}")
        self.resource_id = resource_id


def resolve_resource_id(store: SessionStore, id_or_slug: str) -> str | None:
    if not id_or_slug:
        return None
    r = store.get_repo_resource(id_or_slug)
    if r:
        return r["id"]
    r = store.get_repo_resource_by_slug(id_or_slug)
    if r:
        return r["id"]
    if "." in id_or_slug and "/" not in id_or_slug:
        candidate = id_or_slug.replace(".", "/")
        r = store.get_repo_resource_by_slug(candidate)
        if r:
            return r["id"]
    return None


def _resolve_or_raise(store: SessionStore, id_or_slug: str) -> str:
    rid = resolve_resource_id(store, id_or_slug)
    if rid is None:
        raise ResourceNotFound(id_or_slug)
    return rid


def _active_version_or_raise(store: SessionStore, resource_id: str) -> dict:
    active = store.get_active_repo_version(resource_id)
    if not active:
        raise NoActiveVersion(resource_id)
    return active


def list_resources(
    *,
    store: SessionStore,
    type: ResourceType | None = None,
    query: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return {
        "items": store.list_repo_resources(
            type=type, query=query, include_deleted=include_deleted, limit=limit, offset=offset,
        ),
        "total": store.count_repo_resources(type=type, query=query, include_deleted=include_deleted),
        "limit": limit,
        "offset": offset,
    }


def create_resource(
    *,
    store: SessionStore,
    slug: str,
    type: ResourceType,
    display_name: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> RepoResourceRow:
    try:
        result = store.create_repo_resource(
            slug=slug, type=type, display_name=display_name, description=description, tags=tags or [],
        )
        return cast(RepoResourceRow, result)
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def get_resource(resource_id: str, *, store: SessionStore) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    r = store.get_repo_resource(rid)
    active = store.get_active_repo_version(rid) if r and r.get("active_version_id") else None
    return {"resource": r, "active_version": active}


def update_resource(resource_id: str, *, store: SessionStore, display_name: str | None = None, description: str | None = None, tags: list[str] | None = None) -> RepoResourceRow:
    rid = _resolve_or_raise(store, resource_id)
    updated = store.update_repo_resource(rid, display_name=display_name, description=description, tags=tags)
    if updated is None:
        raise ResourceNotFound(resource_id)
    return updated


def list_versions(resource_id: str, *, store: SessionStore) -> dict:
    rid = _resolve_or_raise(store, resource_id)
    return {"items": store.list_repo_versions(rid)}


def publish_version(resource_id: str, version_id: str, *, store: SessionStore, reason: str, actor: str | None = None) -> dict:
    v = store.get_repo_version(version_id)
    if not v or v["resource_id"] != resource_id:
        raise ResourceNotFound(version_id)
    try:
        return store.publish_repo_version(version_id, reason=reason, activated_by=actor)
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def rollback_resource(resource_id: str, *, store: SessionStore, target_version: int, reason: str, actor: str | None = None) -> dict:
    _require_resource(store, resource_id)
    try:
        return store.rollback_repo_resource(resource_id, target_version, reason=reason, activated_by=actor)
    except ValueError as exc:
        raise InvalidResource(str(exc)) from exc


def soft_delete_resource(resource_id: str, *, store: SessionStore, reason: str) -> None:
    _require_resource(store, resource_id)
    store.soft_delete_repo_resource(resource_id, reason=reason)


def _require_resource(store: SessionStore, resource_id: str) -> RepoResourceRow:
    resource = store.get_repo_resource(resource_id)
    if not resource:
        raise ResourceNotFound(resource_id)
    return resource


def list_repo_resources(store: SessionStore, *, type: str | None = None, limit: int = 50) -> list[dict]:
    return store.list_repo_resources(type=type, limit=limit)


def get_repo_resource_by_slug(store: SessionStore, slug: str) -> RepoResourceRow | None:
    result = store.get_repo_resource_by_slug(slug)
    return cast("RepoResourceRow | None", result)


def create_repo_resource(store: SessionStore, slug: str, type: str, display_name: str, *, description: str | None = None, tags: list[str] | None = None, created_by: str | None = None) -> RepoResourceRow:
    result = store.create_repo_resource(slug, type, display_name, description=description, tags=tags, created_by=created_by)
    return cast(RepoResourceRow, result)


def list_repo_versions(store: SessionStore, resource_id: str) -> list[dict]:
    return store.list_repo_versions(resource_id)


def import_repo_version(store: SessionStore, resource_id: str, blobs: list[tuple[str, bytes, str | None, str | None]], *, import_source: str, changelog: str, source_metadata: dict | None = None, metadata: dict | None = None, draft: bool = False, created_by: str | None = None, activate: bool = True) -> dict:
    return store.import_repo_version(resource_id, blobs, import_source=import_source, changelog=changelog, source_metadata=source_metadata, metadata=metadata, draft=draft, created_by=created_by, activate=activate)


def publish_repo_version(store: SessionStore, version_id: str, *, reason: str, activated_by: str | None = None) -> dict:
    return store.publish_repo_version(version_id, reason=reason, activated_by=activated_by)


def rollback_repo_resource(store: SessionStore, resource_id: str, target_version: int, *, reason: str, activated_by: str | None = None) -> dict:
    return store.rollback_repo_resource(resource_id, target_version, reason=reason, activated_by=activated_by)


def list_prompt_bindings(store: SessionStore, agent_id: str) -> list[dict]:
    return store.list_prompt_bindings(agent_id)


def replace_prompt_bindings(store: SessionStore, agent_id: str, bindings: list[dict], *, reason: str, actor: str | None = None) -> list[dict]:
    return store.replace_prompt_bindings(agent_id, bindings, reason=reason, actor=actor)
