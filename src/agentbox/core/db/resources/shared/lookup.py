"""Read-only methods for SharedResourcesMixin."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Engine

from agentbox.core.db.schema import shared_resources
from agentbox.core.db.resources.shared._models import (
    SharedResourceRecord,
    row_to_record,
)


class SharedResourceLookupMixin:
    """Read-only shared resource access. Requires ``self.engine: Engine``."""

    engine: Engine

    def get_resource(self, id: str, version: int) -> SharedResourceRecord | None:
        """Fetch a specific resource version by id and version number."""
        with self.engine.connect() as conn:
            row = conn.execute(
                shared_resources.select().where(
                    and_(
                        shared_resources.c.id == id,
                        shared_resources.c.version == version,
                    )
                )
            ).first()
            return row_to_record(row._mapping) if row else None

    def get_active_resource(self, id: str) -> SharedResourceRecord | None:
        """Fetch the active version of a resource."""
        with self.engine.connect() as conn:
            row = conn.execute(
                shared_resources.select()
                .where(
                    and_(
                        shared_resources.c.id == id,
                        shared_resources.c.is_active == 1,
                    )
                )
                .limit(1)
            ).first()
            return row_to_record(row._mapping) if row else None

    def list_resources(
        self,
        *,
        kind: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SharedResourceRecord]:
        """List active resources, optionally filtered by kind and search text."""
        with self.engine.connect() as conn:
            query = (
                shared_resources.select()
                .where(shared_resources.c.is_active == 1)
                .order_by(shared_resources.c.created_at.desc())
            )

            if kind:
                query = query.where(shared_resources.c.kind == kind)

            if q:
                query = query.where(
                    or_(
                        shared_resources.c.name.ilike(f"%{q}%"),
                        shared_resources.c.description.ilike(f"%{q}%"),
                    )
                )

            query = query.limit(limit).offset(offset)

            rows = conn.execute(query)
            records = [row_to_record(r._mapping) for r in rows]
            return [r for r in records if r is not None]

    def count_active_resources(
        self, *, kind: str | None = None, q: str | None = None
    ) -> int:
        """Mirror of ``list_resources`` filters, returning a row count."""
        with self.engine.connect() as conn:
            query = (
                select(func.count())
                .select_from(shared_resources)
                .where(shared_resources.c.is_active == 1)
            )
            if kind:
                query = query.where(shared_resources.c.kind == kind)
            if q:
                query = query.where(
                    or_(
                        shared_resources.c.name.ilike(f"%{q}%"),
                        shared_resources.c.description.ilike(f"%{q}%"),
                    )
                )
            return int(conn.execute(query).scalar() or 0)

    def list_resource_versions(
        self, id: str, *, limit: int = 50, offset: int = 0
    ) -> list[SharedResourceRecord]:
        """List all versions of a resource."""
        with self.engine.connect() as conn:
            rows = conn.execute(
                shared_resources.select()
                .where(shared_resources.c.id == id)
                .order_by(shared_resources.c.version.desc())
                .limit(limit)
                .offset(offset)
            )
            records = [row_to_record(r._mapping) for r in rows]
            return [r for r in records if r is not None]


class SharedResourceLookupSurface(Protocol):
    """Type-only view of SharedResourceLookupMixin for sibling-mixin self-binding.

    Sibling mixins call into the lookup surface via ``self.<method>`` at runtime;
    pyright cannot see through the MRO across split files. Consumers declare
    ``self: SharedResourceLookupSurface`` so pyright resolves the calls. Runtime
    behavior is unaffected.
    """

    def get_resource(self, id: str, version: int) -> SharedResourceRecord | None: ...
    def get_active_resource(self, id: str) -> SharedResourceRecord | None: ...
