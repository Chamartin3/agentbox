"""Resource, ResourceVersion, ResourceBlob, and ActiveResourceVersion managers."""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from typing import cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Connection

from agentbox.core.data.constants import ImportSource, ResourceType
from agentbox.core.data.rows import RepoResourceRow, ResourceBlobRow, ResourceVersionRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.resources.resource import (
    ActiveResourceVersion,
    Resource,
    ResourceBlob,
    ResourceVersion,
)
from agentbox.core.db.schema import (
    active_resource_versions,
    resource_blobs,
    resource_versions,
    resources as resources_table,
)
from agentbox.core.data._util import now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIN_CHANGELOG = 3


def _validate_changelog(changelog: str) -> str:
    if not changelog or len(changelog.strip()) < _MIN_CHANGELOG:
        raise ValueError(
            f"changelog/reason must be at least {_MIN_CHANGELOG} characters"
        )
    return changelog.strip()


def _tags_to_db(tags: list[str] | None) -> str | None:
    if not tags:
        return None
    return ",".join(t.strip() for t in tags if t and t.strip())


def _hash_blobs(blobs: list[tuple[str, bytes]]) -> str:
    h = hashlib.sha256()
    for rel_path, content in sorted(blobs, key=lambda b: b[0]):
        h.update(rel_path.encode("utf-8"))
        h.update(b"\x00")
        h.update(hashlib.sha256(content).digest())
        h.update(b"\x00")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# ResourceManager
# ---------------------------------------------------------------------------


class ResourceManager(Manager[Resource]):
    """Manager for the ``resources`` table."""

    model = Resource

    def create_resource(
        self,
        slug: str,
        type: str,
        display_name: str,
        *,
        description: str | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
    ) -> RepoResourceRow:
        """Insert a new resource row and return it as a typed row."""
        ResourceType.coerce(type, label="resource type")
        if not slug or not slug.strip():
            raise ValueError("slug is required")
        rid = uuid.uuid4().hex
        now = now_iso()
        with self._engine.begin() as conn:
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
        result = self.get_resource(rid)
        assert result is not None, f"just-inserted resource {rid!r} must be retrievable"
        return result

    def get_resource(self, resource_id: str) -> RepoResourceRow | None:
        """Fetch a resource row by id. Returns a typed row or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                resources_table.select().where(resources_table.c.id == resource_id)
            ).first()
            return cast(RepoResourceRow, dict(row._mapping)) if row else None

    def get_by_slug(self, slug: str) -> RepoResourceRow | None:
        """Fetch a resource row by slug. Returns a typed row or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                resources_table.select().where(resources_table.c.slug == slug)
            ).first()
            return cast(RepoResourceRow, dict(row._mapping)) if row else None

    def update_resource(
        self,
        resource_id: str,
        *,
        type: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> RepoResourceRow | None:
        """Update mutable resource fields. Returns updated typed row or None."""
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
            return self.get_resource(resource_id)
        values["updated_at"] = now_iso()
        with self._engine.begin() as conn:
            conn.execute(
                resources_table.update()
                .where(resources_table.c.id == resource_id)
                .values(**values)
            )
        return self.get_resource(resource_id)

    def list_resources(
        self,
        *,
        type: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RepoResourceRow]:
        """List resource rows with optional filters."""
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
        with self._engine.connect() as conn:
            return [cast(RepoResourceRow, dict(r._mapping)) for r in conn.execute(stmt)]

    def count_resources(
        self,
        *,
        type: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        """Count resource rows matching filters."""
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
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return int(row[0]) if row else 0

    def soft_delete(self, resource_id: str, *, reason: str) -> None:
        """Set status='deleted' on a resource row."""
        _validate_changelog(reason)
        with self._engine.begin() as conn:
            conn.execute(
                resources_table.update()
                .where(resources_table.c.id == resource_id)
                .values(status="deleted", updated_at=now_iso())
            )

    def _set_active_version(self, conn: Connection, resource_id: str, version_id: str, *, now: str) -> None:
        """Update the active_version_id on the resources row (called within an open conn)."""
        conn.execute(
            resources_table.update()
            .where(resources_table.c.id == resource_id)
            .values(active_version_id=version_id, updated_at=now)
        )


# ---------------------------------------------------------------------------
# ResourceVersionManager
# ---------------------------------------------------------------------------


class ResourceVersionManager(Manager[ResourceVersion]):
    """Manager for the ``resource_versions`` table.

    Owns atomic multi-table operations: import (version + blobs), publish,
    rollback. Each of these writes across resource_versions, resource_blobs,
    and active_resource_versions in a single transaction.
    """

    model = ResourceVersion

    def get_version(self, version_id: str) -> ResourceVersionRow | None:
        """Fetch a version row by id. Returns typed row or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                resource_versions.select().where(resource_versions.c.id == version_id)
            ).first()
            return cast(ResourceVersionRow, dict(row._mapping)) if row else None

    def list_versions(self, resource_id: str) -> list[ResourceVersionRow]:
        """Return all versions for a resource ordered by version_number desc."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                resource_versions.select()
                .where(resource_versions.c.resource_id == resource_id)
                .order_by(resource_versions.c.version_number.desc())
            )
            return [cast(ResourceVersionRow, dict(r._mapping)) for r in rows]

    def _next_version_number(self, resource_id: str) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(
                    func.coalesce(func.max(resource_versions.c.version_number), 0)
                ).where(resource_versions.c.resource_id == resource_id)
            ).first()
        return int(row[0]) + 1 if row else 1

    def _activate_in_conn(
        self,
        conn: Connection,
        resource_id: str,
        version_id: str,
        *,
        activated_by: str | None,
        now: str,
    ) -> None:
        """Atomically swap the active pointer (delete old, insert new) within conn."""
        conn.execute(
            active_resource_versions.delete().where(
                active_resource_versions.c.resource_id == resource_id
            )
        )
        conn.execute(
            active_resource_versions.insert().values(
                resource_id=resource_id,
                version_id=version_id,
                activated_at=now,
                activated_by=activated_by,
            )
        )
        conn.execute(
            resources_table.update()
            .where(resources_table.c.id == resource_id)
            .values(active_version_id=version_id, updated_at=now)
        )

    def import_version(
        self,
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
    ) -> ResourceVersionRow:
        """Create a new resource version with blobs (atomic).

        Writes to resource_versions, resource_blobs, and (if activate) to
        active_resource_versions and resources in a single transaction.
        """
        ImportSource.coerce(import_source, label="import_source")
        changelog = _validate_changelog(changelog)

        # Verify resource exists
        with self._engine.connect() as conn:
            rrow = conn.execute(
                resources_table.select().where(resources_table.c.id == resource_id)
            ).first()
            if not rrow:
                raise ValueError(f"Resource {resource_id!r} not found")

        hash_input = [(b[0], b[1]) for b in blobs]
        content_hash = _hash_blobs(hash_input)
        byte_size = sum(len(b[1]) for b in blobs)
        version_number = self._next_version_number(resource_id)
        vid = uuid.uuid4().hex
        now = now_iso()

        with self._engine.begin() as conn:
            conn.execute(
                resource_versions.insert().values(
                    id=vid,
                    resource_id=resource_id,
                    version_number=version_number,
                    is_draft=1 if draft else 0,
                    import_source=import_source,
                    source_metadata=json.dumps(source_metadata) if source_metadata is not None else None,
                    content_hash=content_hash,
                    byte_size=byte_size,
                    metadata_json=json.dumps(metadata) if metadata is not None else None,
                    changelog=changelog,
                    created_at=now,
                    created_by=created_by,
                )
            )
            for rel_path, content, mime_type, content_text in blobs:
                conn.execute(
                    resource_blobs.insert().values(
                        id=uuid.uuid4().hex,
                        resource_version_id=vid,
                        relative_path=rel_path,
                        content=content,
                        content_text=content_text,
                        mime_type=mime_type,
                        size_bytes=len(content),
                    )
                )
            if activate and not draft:
                self._activate_in_conn(conn, resource_id, vid, activated_by=created_by, now=now)

        result = self.get_version(vid)
        assert result is not None, f"just-inserted version {vid!r} must be retrievable"
        return result

    def publish_version(
        self, version_id: str, *, reason: str, activated_by: str | None = None
    ) -> ResourceVersionRow:
        """Promote a draft to active (atomic: flips is_draft=0, activates pointer)."""
        _validate_changelog(reason)
        version = self.get_version(version_id)
        if not version:
            raise ValueError(f"Version {version_id!r} not found")
        now = now_iso()
        with self._engine.begin() as conn:
            conn.execute(
                resource_versions.update()
                .where(resource_versions.c.id == version_id)
                .values(is_draft=0, changelog=reason)
            )
            self._activate_in_conn(
                conn, version["resource_id"], version_id, activated_by=activated_by, now=now
            )
        result = self.get_version(version_id)
        assert result is not None, f"version {version_id!r} must exist after publish"
        return result

    def rollback_resource(
        self,
        resource_id: str,
        target_version: int,
        *,
        reason: str,
        activated_by: str | None = None,
    ) -> ResourceVersionRow:
        """Create a new version copying blobs from ``target_version`` (atomic)."""
        reason = _validate_changelog(reason)
        with self._engine.connect() as conn:
            row = conn.execute(
                resource_versions.select().where(
                    resource_versions.c.resource_id == resource_id,
                    resource_versions.c.version_number == target_version,
                )
            ).first()
            if not row:
                raise ValueError(
                    f"Version {target_version} not found for resource {resource_id!r}"
                )
            if row._mapping["is_draft"]:
                raise ValueError(f"Cannot rollback to a draft version ({target_version})")
            target_vid = row._mapping["id"]
            blob_rows = list(
                conn.execute(
                    resource_blobs.select().where(
                        resource_blobs.c.resource_version_id == target_vid
                    )
                )
            )
        blobs = [
            (
                b._mapping["relative_path"],
                b._mapping["content"],
                b._mapping.get("mime_type"),
                b._mapping.get("content_text"),
            )
            for b in blob_rows
        ]
        return self.import_version(
            resource_id,
            blobs,
            import_source="db_only",
            changelog=f"Rollback to version {target_version}: {reason}",
            metadata={"rolled_back_from": target_version},
            draft=False,
            created_by=activated_by,
            activate=True,
        )

    def get_active_version_id(self, resource_id: str) -> str | None:
        """Return the currently active version_id for a resource, or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                active_resource_versions.select().where(
                    active_resource_versions.c.resource_id == resource_id
                )
            ).first()
            return row._mapping["version_id"] if row else None

    def get_active_version(self, resource_id: str) -> ResourceVersionRow | None:
        """Return the currently active version row as a typed row, or None."""
        vid = self.get_active_version_id(resource_id)
        if not vid:
            return None
        return self.get_version(vid)


# ---------------------------------------------------------------------------
# ResourceBlobManager
# ---------------------------------------------------------------------------


class ResourceBlobManager(Manager[ResourceBlob]):
    """Manager for the ``resource_blobs`` table."""

    model = ResourceBlob

    def get_blob(self, version_id: str, relative_path: str = "") -> ResourceBlobRow | None:
        """Fetch a single blob by version and relative_path."""
        with self._engine.connect() as conn:
            row = conn.execute(
                resource_blobs.select().where(
                    resource_blobs.c.resource_version_id == version_id,
                    resource_blobs.c.relative_path == relative_path,
                )
            ).first()
            return cast(ResourceBlobRow, dict(row._mapping)) if row else None

    def iter_blobs(self, version_id: str) -> Iterator[ResourceBlobRow]:
        """Yield all blobs for a version ordered by relative_path."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                resource_blobs.select()
                .where(resource_blobs.c.resource_version_id == version_id)
                .order_by(resource_blobs.c.relative_path)
            )
            for r in rows:
                yield cast(ResourceBlobRow, dict(r._mapping))


# ---------------------------------------------------------------------------
# ActiveResourceVersionManager
# ---------------------------------------------------------------------------


class ActiveResourceVersionManager(Manager[ActiveResourceVersion]):
    """Manager for the ``active_resource_versions`` table."""

    model = ActiveResourceVersion
