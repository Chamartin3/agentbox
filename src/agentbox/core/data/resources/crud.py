"""Resources mixin: CRUD + version lifecycle for the central resource repo.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``resources``, ``resource_versions``, ``resource_blobs``, and
``active_resource_versions``. Mirrors the patterns in
``PromptVersionsMixin``.

Public methods return plain dicts (and ``Resource*`` dataclasses for
typed callers). All write operations that produce a new version require
a ``changelog`` (also called ``reason`` in the API layer) of at least
3 characters — mirroring the prompt-version audit story.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Iterator

from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.row_types import RepoResourceRow
from agentbox.core.data.schema import (
    active_resource_versions,
    resource_blobs,
    resource_versions,
)
from agentbox.core.data.schema import (
    resources as resources_table,
)
from agentbox.core.data.resources.models import (
    IMPORT_SOURCES,
    RESOURCE_TYPES,
    Resource,
    ResourceBlob,
    ResourceVersion,
)

_MIN_CHANGELOG = 3


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_blobs(blobs: Iterable[tuple[str, bytes]]) -> str:
    """Deterministic hash over a (relative_path, content) sequence."""
    h = hashlib.sha256()
    for rel_path, content in sorted(blobs, key=lambda b: b[0]):
        h.update(rel_path.encode("utf-8"))
        h.update(b"\x00")
        h.update(hashlib.sha256(content).digest())
        h.update(b"\x00")
    return h.hexdigest()


def _validate_changelog(changelog: str) -> str:
    if not changelog or len(changelog.strip()) < _MIN_CHANGELOG:
        raise ValueError(
            f"changelog/reason must be at least {_MIN_CHANGELOG} characters"
        )
    return changelog.strip()


def _tags_to_db(tags: Iterable[str] | None) -> str | None:
    if not tags:
        return None
    return ",".join(t.strip() for t in tags if t and t.strip())


def _tags_from_db(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(t for t in (s.strip() for s in raw.split(",")) if t)


def _row_to_resource(row) -> Resource:
    m = row._mapping
    return Resource(
        id=m["id"],
        slug=m["slug"],
        type=m["type"],
        display_name=m["display_name"],
        description=m.get("description"),
        tags=_tags_from_db(m.get("tags")),
        active_version_id=m.get("active_version_id"),
        status=m.get("status") or "active",
        created_at=m["created_at"],
        updated_at=m["updated_at"],
        created_by=m.get("created_by"),
    )


def _row_to_version(row) -> ResourceVersion:
    m = row._mapping
    return ResourceVersion(
        id=m["id"],
        resource_id=m["resource_id"],
        version_number=m["version_number"],
        is_draft=bool(m["is_draft"]),
        import_source=m["import_source"],
        source_metadata=json.loads(m["source_metadata"])
        if m.get("source_metadata")
        else None,
        content_hash=m["content_hash"],
        byte_size=int(m.get("byte_size") or 0),
        metadata=json.loads(m["metadata_json"]) if m.get("metadata_json") else None,
        changelog=m["changelog"],
        created_at=m["created_at"],
        created_by=m.get("created_by"),
    )


def _row_to_blob(row) -> ResourceBlob:
    m = row._mapping
    return ResourceBlob(
        id=m["id"],
        resource_version_id=m["resource_version_id"],
        relative_path=m["relative_path"],
        content=m["content"],
        content_text=m.get("content_text"),
        mime_type=m.get("mime_type"),
        size_bytes=int(m.get("size_bytes") or 0),
    )


class ResourcesMixin:
    """Versioned resource repository. Requires ``self.engine: Engine``."""

    engine: Engine

    # --- create / read ---

    def create_repo_resource(
        self,
        slug: str,
        type: str,
        display_name: str,
        *,
        description: str | None = None,
        tags: Iterable[str] | None = None,
        created_by: str | None = None,
    ) -> RepoResourceRow | dict:
        if type not in RESOURCE_TYPES:
            raise ValueError(
                f"Invalid resource type {type!r}; must be one of {RESOURCE_TYPES}"
            )
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
        tags: Iterable[str] | None = None,
    ) -> RepoResourceRow | None:
        """Update mutable resource fields. Pass only the fields you want to change."""
        values: dict = {}
        if type is not None:
            if type not in RESOURCE_TYPES:
                raise ValueError(
                    f"Invalid resource type {type!r}; must be one of {RESOURCE_TYPES}"
                )
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

    # --- versions ---

    def _next_version_number(self, resource_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(
                    func.coalesce(func.max(resource_versions.c.version_number), 0)
                ).where(resource_versions.c.resource_id == resource_id)
            ).first()
        return int(row[0]) + 1 if row else 1

    def import_repo_version(
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
    ) -> dict:
        """Create a new resource version.

        ``blobs`` is a list of ``(relative_path, content_bytes, mime_type,
        content_text)`` tuples. For ``document`` resources pass a single
        blob with ``relative_path=""``.
        """
        if import_source not in IMPORT_SOURCES:
            raise ValueError(
                f"Invalid import_source {import_source!r}; must be one of {IMPORT_SOURCES}"
            )
        changelog = _validate_changelog(changelog)
        if not self.get_repo_resource(resource_id):
            raise ValueError(f"Resource {resource_id!r} not found")

        hash_input = [(b[0], b[1]) for b in blobs]
        content_hash = _hash_blobs(hash_input)
        byte_size = sum(len(b[1]) for b in blobs)
        version_number = self._next_version_number(resource_id)
        vid = uuid.uuid4().hex
        now = now_iso()

        with self.engine.begin() as conn:
            conn.execute(
                resource_versions.insert().values(
                    id=vid,
                    resource_id=resource_id,
                    version_number=version_number,
                    is_draft=1 if draft else 0,
                    import_source=import_source,
                    source_metadata=json.dumps(source_metadata)
                    if source_metadata is not None
                    else None,
                    content_hash=content_hash,
                    byte_size=byte_size,
                    metadata_json=json.dumps(metadata)
                    if metadata is not None
                    else None,
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
                self._activate_version_in_conn(
                    conn, resource_id, vid, activated_by=created_by
                )

        return self.get_repo_version(vid) or {}

    def get_repo_version(self, version_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                resource_versions.select().where(resource_versions.c.id == version_id)
            ).first()
            return dict(row._mapping) if row else None

    def list_repo_versions(self, resource_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                resource_versions.select()
                .where(resource_versions.c.resource_id == resource_id)
                .order_by(resource_versions.c.version_number.desc())
            )
            return [dict(r._mapping) for r in rows]

    def get_active_repo_version(self, resource_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                active_resource_versions.select().where(
                    active_resource_versions.c.resource_id == resource_id
                )
            ).first()
            if not row:
                return None
            vid = row._mapping["version_id"]
        return self.get_repo_version(vid)

    def _activate_version_in_conn(
        self,
        conn,
        resource_id: str,
        version_id: str,
        *,
        activated_by: str | None = None,
    ) -> None:
        now = now_iso()
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

    def publish_repo_version(
        self, version_id: str, *, reason: str, activated_by: str | None = None
    ) -> dict:
        """Promote a draft version to active."""
        _validate_changelog(reason)
        version = self.get_repo_version(version_id)
        if not version:
            raise ValueError(f"Version {version_id!r} not found")
        with self.engine.begin() as conn:
            conn.execute(
                resource_versions.update()
                .where(resource_versions.c.id == version_id)
                .values(is_draft=0, changelog=reason)
            )
            self._activate_version_in_conn(
                conn, version["resource_id"], version_id, activated_by=activated_by
            )
        return self.get_repo_version(version_id) or {}

    def rollback_repo_resource(
        self,
        resource_id: str,
        target_version: int,
        *,
        reason: str,
        activated_by: str | None = None,
    ) -> dict:
        """Create a new version copying the blobs of ``target_version``."""
        reason = _validate_changelog(reason)
        with self.engine.connect() as conn:
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
                raise ValueError(
                    f"Cannot rollback to a draft version ({target_version})"
                )
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
        return self.import_repo_version(
            resource_id,
            blobs,
            import_source="db_only",
            changelog=f"Rollback to version {target_version}: {reason}",
            metadata={"rolled_back_from": target_version},
            draft=False,
            created_by=activated_by,
            activate=True,
        )

    # --- blobs ---

    def read_repo_blob(self, version_id: str, relative_path: str = "") -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                resource_blobs.select().where(
                    resource_blobs.c.resource_version_id == version_id,
                    resource_blobs.c.relative_path == relative_path,
                )
            ).first()
            return dict(row._mapping) if row else None

    def iter_repo_blobs(self, version_id: str) -> Iterator[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                resource_blobs.select()
                .where(resource_blobs.c.resource_version_id == version_id)
                .order_by(resource_blobs.c.relative_path)
            )
            for r in rows:
                yield dict(r._mapping)

    # --- deletion ---

    def soft_delete_repo_resource(self, resource_id: str, *, reason: str) -> None:
        _validate_changelog(reason)
        with self.engine.begin() as conn:
            conn.execute(
                resources_table.update()
                .where(resources_table.c.id == resource_id)
                .values(status="deleted", updated_at=now_iso())
            )

    # --- introspection helpers ---

    def get_active_repo_hash(self, resource_id: str) -> str | None:
        v = self.get_active_repo_version(resource_id)
        return v["content_hash"] if v else None
