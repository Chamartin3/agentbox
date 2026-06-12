"""Repo-resource CRUD mixin for ResourcesMixin."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Engine

from agentbox.core.data.utils import now_iso
from agentbox.core.data.row_types import RepoResourceRow
from agentbox.core.constants import ResourceType
from agentbox.core.data.schema import (
    resources as resources_table,
)
from agentbox.core.data.resources.crud._helpers import (
    _tags_to_db,
    _validate_changelog,
)
from agentbox.core.data.resources.crud._versions import CrudVersionSurface


class ResourceCrudMixin:
    """Repo-resource CRUD operations. Requires ``self.engine: Engine``."""

    engine: Engine

    def create_repo_resource(
        self,
        slug: str,
        type: str,
        display_name: str,
        *,
        description: str | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
    ) -> RepoResourceRow | dict:
        ResourceType.coerce(type, label="resource type")
        if not slug or not slug.strip():
            raise ValueError("slug is required")
        rid = uuid.uuid4().hex
        now = now_iso()
        with self.engine.begin() as conn:
            conn.execute(
                resources_table.insert().values(
                    id=rid,
                    slug=slug.strip(),
                    type=type,
                    display_name=display_name,
                    description=description,
                    tags=_tags_to_db(tags),
                    active_version_id=None,
                    status="active",
                    created_at=now,
                    updated_at=now,
                    created_by=created_by,
                )
            )
        return self.get_repo_resource(rid) or {}

    def update_repo_resource(
        self,
        resource_id: str,
        *,
        type: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> RepoResourceRow | None:
        """Update mutable resource fields."""
        values: dict = {}
        if type is not None:
            ResourceType.coerce(type, label="resource type")
            values["type"] = type
        if display_name is not None:
            values["display_name"] = display_name
        if description is not None:
            values["description"] = description
        if tags is not None:
            values["tags"] = _tags_to_db(tags)
        if not values:
            return self.get_repo_resource(resource_id)
        values["updated_at"] = now_iso()
        with self.engine.begin() as conn:
            conn.execute(
                resources_table.update()
                .where(resources_table.c.id == resource_id)
                .values(**values)
            )
        return self.get_repo_resource(resource_id)

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                resources_table.select().where(resources_table.c.id == resource_id)
            ).first()
            return RepoResourceRow(**dict(row._mapping)) if row else None

    def get_repo_resource_by_slug(self, slug: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                resources_table.select().where(resources_table.c.slug == slug)
            ).first()
            return dict(row._mapping) if row else None

    def list_repo_resources(
        self,
        *,
        type: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = resources_table.select()
        clauses = []
        if not include_deleted:
            clauses.append(resources_table.c.status == "active")
        if type:
            clauses.append(resources_table.c.type == type)
        if query:
            like = f"%{query.lower()}%"
            clauses.append(
                or_(
                    func.lower(resources_table.c.slug).like(like),
                    func.lower(resources_table.c.display_name).like(like),
                )
            )
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = (
            stmt.order_by(resources_table.c.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt)]

    def count_repo_resources(
        self,
        *,
        type: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        stmt = select(func.count()).select_from(resources_table)
        clauses = []
        if not include_deleted:
            clauses.append(resources_table.c.status == "active")
        if type:
            clauses.append(resources_table.c.type == type)
        if query:
            like = f"%{query.lower()}%"
            clauses.append(
                or_(
                    func.lower(resources_table.c.slug).like(like),
                    func.lower(resources_table.c.display_name).like(like),
                )
            )
        if clauses:
            stmt = stmt.where(and_(*clauses))
        with self.engine.connect() as conn:
            row = conn.execute(stmt).first()
        return int(row[0]) if row else 0

    def soft_delete_repo_resource(self, resource_id: str, *, reason: str) -> None:
        _validate_changelog(reason)
        with self.engine.begin() as conn:
            conn.execute(
                resources_table.update()
                .where(resources_table.c.id == resource_id)
                .values(status="deleted", updated_at=now_iso())
            )

    def get_active_repo_hash(self: "CrudVersionSurface", resource_id: str) -> str | None:
        v = self.get_active_repo_version(resource_id)
        return v["content_hash"] if v else None


class CrudRepoSurface(Protocol):
    """Type-only view of ResourceCrudMixin for sibling-mixin self-binding."""

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None: ...
