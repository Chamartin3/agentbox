"""Service layer for repo-resource and prompt-binding pass-through CRUD.

Thin wrappers around ``SessionStore`` methods used by
``cli/resources/repo.py`` and ``cli/resources/bindings.py``.
No validation — pure delegation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore

__all__ = [
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


def list_repo_resources(
    store: SessionStore,
    *,
    type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return store.list_repo_resources(type=type, limit=limit)


def get_repo_resource_by_slug(store: SessionStore, slug: str) -> dict | None:
    return store.get_repo_resource_by_slug(slug)


def create_repo_resource(
    store: SessionStore,
    slug: str,
    type: str,
    display_name: str,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
    created_by: str | None = None,
) -> dict:
    return store.create_repo_resource(
        slug,
        type,
        display_name,
        description=description,
        tags=tags,
        created_by=created_by,
    )


def list_repo_versions(store: SessionStore, resource_id: str) -> list[dict]:
    return store.list_repo_versions(resource_id)


def import_repo_version(
    store: SessionStore,
    resource_id: str,
    blobs: list[tuple[str, bytes, str | None, str | None]],
    *,
    import_source: str,
    changelog: str,
    source_metadata: dict | None = None,
    metadata: dict | None = None,
    draft: bool = False,
    created_by: str | None = None,
    activate: bool = True,
) -> dict:
    return store.import_repo_version(
        resource_id,
        blobs,
        import_source=import_source,
        changelog=changelog,
        source_metadata=source_metadata,
        metadata=metadata,
        draft=draft,
        created_by=created_by,
        activate=activate,
    )


def publish_repo_version(
    store: SessionStore,
    version_id: str,
    *,
    reason: str,
    activated_by: str | None = None,
) -> dict:
    return store.publish_repo_version(
        version_id, reason=reason, activated_by=activated_by
    )


def rollback_repo_resource(
    store: SessionStore,
    resource_id: str,
    target_version: int,
    *,
    reason: str,
    activated_by: str | None = None,
) -> dict:
    return store.rollback_repo_resource(
        resource_id, target_version, reason=reason, activated_by=activated_by
    )


def list_prompt_bindings(store: SessionStore, agent_id: str) -> list[dict]:
    return store.list_prompt_bindings(agent_id)


def replace_prompt_bindings(
    store: SessionStore,
    agent_id: str,
    bindings: list[dict],
    *,
    reason: str,
    actor: str | None = None,
) -> list[dict]:
    return store.replace_prompt_bindings(
        agent_id, bindings, reason=reason, actor=actor
    )
