"""SharedResource model + manager — cross-repository resource sharing.

Maps to the ``shared_resources`` table.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlmodel import Field, Index

from agentbox.core.data.records import SharedResourceRecord, row_to_shared_resource as row_to_record
from agentbox.core.data._util import now_iso
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs


class SharedResource(Entity, table=True):
    """A resource shared across repositories, versioned by an id+version composite key."""

    __tablename__ = tablename("shared_resources")

    id: str = Field(primary_key=True)
    version: int = Field(primary_key=True)
    kind: str = Field(nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    config_json: Optional[str] = Field(default=None)
    sha256: str = Field(nullable=False)
    is_active: int = Field(nullable=False, default=0, sa_column_kwargs={"server_default": "0"})
    author: Optional[str] = Field(default=None)
    changelog: Optional[str] = Field(default=None)
    tags: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(
        Index("pk_shared_resources", "id", "version", unique=True),
        Index("ix_shared_resources_kind_active", "kind", "is_active"),
        Index("ix_shared_resources_id_active", "id", "is_active"),
    )


shared_resources = SharedResource.__table__


def _compute_sha256(content: str | None, config_json: str | None) -> str:
    h = hashlib.sha256()
    for v in (content, config_json):
        if v is not None:
            h.update(v.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


class SharedResourceManager(Manager[SharedResource]):
    """Manager for the ``shared_resources`` table (composite PK id+version)."""

    model = SharedResource

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_versioned(self, id: str, version: int) -> SharedResourceRecord | None:
        """Fetch a specific (id, version) row."""
        with self._engine.connect() as conn:
            row = conn.execute(
                shared_resources.select().where(
                    and_(
                        shared_resources.c.id == id,
                        shared_resources.c.version == version,
                    )
                )
            ).first()
            return row_to_record(row._mapping) if row else None

    def get_active(self, id: str) -> SharedResourceRecord | None:
        """Fetch the currently active version of a shared resource."""
        with self._engine.connect() as conn:
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

    def list_active(
        self,
        *,
        kind: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SharedResourceRecord]:
        """List active shared resources with optional filters."""
        stmt = (
            shared_resources.select()
            .where(shared_resources.c.is_active == 1)
            .order_by(shared_resources.c.created_at.desc())
        )
        if kind:
            stmt = stmt.where(shared_resources.c.kind == kind)
        if q:
            stmt = stmt.where(
                or_(
                    shared_resources.c.name.ilike(f"%{q}%"),
                    shared_resources.c.description.ilike(f"%{q}%"),
                )
            )
        stmt = stmt.limit(limit).offset(offset)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt)
            records = [row_to_record(r._mapping) for r in rows]
            return [r for r in records if r is not None]

    def count_active(self, *, kind: str | None = None, q: str | None = None) -> int:
        """Count active shared resources matching filters."""
        stmt = (
            select(func.count())
            .select_from(shared_resources)
            .where(shared_resources.c.is_active == 1)
        )
        if kind:
            stmt = stmt.where(shared_resources.c.kind == kind)
        if q:
            stmt = stmt.where(
                or_(
                    shared_resources.c.name.ilike(f"%{q}%"),
                    shared_resources.c.description.ilike(f"%{q}%"),
                )
            )
        with self._engine.connect() as conn:
            return int(conn.execute(stmt).scalar() or 0)

    def list_versions(
        self, id: str, *, limit: int = 50, offset: int = 0
    ) -> list[SharedResourceRecord]:
        """List all versions of a shared resource."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                shared_resources.select()
                .where(shared_resources.c.id == id)
                .order_by(shared_resources.c.version.desc())
                .limit(limit)
                .offset(offset)
            )
            records = [row_to_record(r._mapping) for r in rows]
            return [r for r in records if r is not None]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _next_version(self, id: str) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(shared_resources.c.version), 0)).where(
                    shared_resources.c.id == id
                )
            ).first()
            return int(row[0]) + 1 if row else 1

    def create_resource(
        self,
        id: str,
        kind: str,
        name: str,
        *,
        description: str | None = None,
        content: str | None = None,
        config_json: str | None = None,
        author: str | None = None,
        changelog: str | None = None,
        tags: list[str] | None = None,
        activate: bool = True,
    ) -> SharedResourceRecord:
        """Create version 1 of a shared resource."""
        sha256 = _compute_sha256(content, config_json)
        tags_json = json.dumps(tags) if tags else None
        with self._engine.begin() as conn:
            conn.execute(
                shared_resources.insert().values(
                    id=id,
                    version=1,
                    kind=kind,
                    name=name,
                    description=description,
                    content=content,
                    config_json=config_json,
                    sha256=sha256,
                    is_active=1 if activate else 0,
                    author=author,
                    changelog=changelog or "",
                    tags=tags_json,
                    created_at=now_iso(),
                )
            )
        result = self.get_versioned(id, 1) or row_to_record(
            {
                "id": id,
                "version": 1,
                "kind": kind,
                "name": name,
                "description": description,
                "content": content,
                "config_json": config_json,
                "sha256": sha256,
                "is_active": 1 if activate else 0,
                "author": author,
                "changelog": changelog or "",
                "tags": tags_json,
                "created_at": now_iso(),
            }
        )
        assert result is not None
        return result

    def create_version(
        self,
        id: str,
        *,
        content: str | None = None,
        config_json: str | None = None,
        author: str | None = None,
        changelog: str | None = None,
        activate: bool = False,
        **fields_to_update,
    ) -> SharedResourceRecord:
        """Append a new version to an existing shared resource."""
        latest = self.get_active(id)
        if not latest and not fields_to_update:
            raise ValueError(f"Resource {id!r} not found and no fields provided")

        next_ver = self._next_version(id)
        kind = fields_to_update.get("kind") or (latest.kind if latest else "")
        name = fields_to_update.get("name") or (latest.name if latest else "")
        description = fields_to_update.get("description") or (latest.description if latest else None)
        tags = fields_to_update.get("tags") or (latest.tags if latest else None)

        if content is None and config_json is None:
            content = latest.content if latest else None
            config_json = latest.config_json if latest else None

        sha256 = _compute_sha256(content, config_json)
        tags_json = json.dumps(list(tags)) if tags else None

        with self._engine.begin() as conn:
            if activate:
                conn.execute(
                    shared_resources.update()
                    .where(shared_resources.c.id == id)
                    .values(is_active=0)
                )
            conn.execute(
                shared_resources.insert().values(
                    id=id,
                    version=next_ver,
                    kind=kind,
                    name=name,
                    description=description,
                    content=content,
                    config_json=config_json,
                    sha256=sha256,
                    is_active=1 if activate else 0,
                    author=author,
                    changelog=changelog or "",
                    tags=tags_json,
                    created_at=now_iso(),
                )
            )
        result = self.get_versioned(id, next_ver) or row_to_record(
            {
                "id": id,
                "version": next_ver,
                "kind": kind,
                "name": name,
                "description": description,
                "content": content,
                "config_json": config_json,
                "sha256": sha256,
                "is_active": 1 if activate else 0,
                "author": author,
                "changelog": changelog or "",
                "tags": tags_json,
                "created_at": now_iso(),
            }
        )
        assert result is not None
        return result

    def activate_version(self, id: str, version: int) -> SharedResourceRecord:
        """Atomically activate one version and deactivate all others."""
        target = self.get_versioned(id, version)
        if not target:
            raise ValueError(f"Resource {id!r} version {version} not found")
        with self._engine.begin() as conn:
            conn.execute(
                shared_resources.update()
                .where(shared_resources.c.id == id)
                .values(is_active=0)
            )
            conn.execute(
                shared_resources.update()
                .where(
                    and_(
                        shared_resources.c.id == id,
                        shared_resources.c.version == version,
                    )
                )
                .values(is_active=1)
            )
        return self.get_versioned(id, version) or target
