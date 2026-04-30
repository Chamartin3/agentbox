"""Shared resources mixin: versioned resource persistence with CRUD + lifecycle.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``shared_resources`` table — independent of run state.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.records import SharedResourceRecord, now_iso
from agentbox.core.data.schema import shared_resources


def _compute_sha256(content: str | None, config_json: str | None) -> str:
    """Compute canonical sha256 from content or config_json."""
    if content is not None:
        canonical = content
    elif config_json is not None:
        # Re-parse and re-dump to ensure consistent JSON serialization
        obj = json.loads(config_json)
        canonical = json.dumps(obj, sort_keys=True)
    else:
        canonical = ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SharedResourcesMixin:
    """Versioned shared resource persistence. Requires ``self.engine: Engine``."""

    engine: Engine

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
        """Create a new resource (version 1) and optionally activate it.

        Args:
            id: Stable resource identifier.
            kind: Resource kind (e.g., 'guideline', 'template').
            name: Human-readable name.
            description: Optional description.
            content: Optional content string (takes precedence over config_json for sha256).
            config_json: Optional JSON config.
            author: Author of the resource.
            changelog: Change description.
            tags: Optional list of string tags.
            activate: If True, set is_active=1; otherwise 0.

        Returns:
            SharedResourceRecord for the created version.
        """
        sha256 = _compute_sha256(content, config_json)
        tags_json = json.dumps(tags) if tags else None

        with self.engine.begin() as conn:
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
        return self.get_resource(id, 1) or self._row_to_record(
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

    def create_resource_version(
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
        """Create a new version of an existing resource.

        Bumps the version number. If activate=True, atomically demotes the
        prior active row and activates this new version.

        Args:
            id: Stable resource identifier.
            content: Updated content (optional).
            config_json: Updated config (optional).
            author: Author of this version.
            changelog: Change description.
            activate: If True, set is_active=1 and demote others.
            **fields_to_update: Additional fields (kind, name, description, tags).

        Returns:
            SharedResourceRecord for the new version.
        """
        # Get current latest version to inherit fields
        latest = self.get_active_resource(id)
        if not latest and not fields_to_update:
            raise ValueError(f"Resource {id!r} not found and no fields provided")

        # Compute new version number
        next_ver = self._next_version(id)

        # Merge field updates with latest values
        kind = fields_to_update.get("kind") or (latest.kind if latest else "")
        name = fields_to_update.get("name") or (latest.name if latest else "")
        description = fields_to_update.get("description") or (
            latest.description if latest else None
        )
        tags = fields_to_update.get("tags") or (latest.tags if latest else None)

        # If neither content nor config_json provided, inherit from latest
        if content is None and config_json is None:
            content = latest.content if latest else None
            config_json = latest.config_json if latest else None

        sha256 = _compute_sha256(content, config_json)
        tags_json = json.dumps(tags) if tags else None

        with self.engine.begin() as conn:
            # If activating, demote others first
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

        return self.get_resource(id, next_ver) or self._row_to_record(
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
            return self._row_to_record(row._mapping) if row else None

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
            return self._row_to_record(row._mapping) if row else None

    def list_resources(
        self,
        *,
        kind: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SharedResourceRecord]:
        """List active resources, optionally filtered by kind and search text.

        Args:
            kind: Optional filter by resource kind.
            q: Optional ILIKE search on name/description.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            List of active SharedResourceRecord.
        """
        with self.engine.connect() as conn:
            query = (
                shared_resources.select()
                .where(shared_resources.c.is_active == 1)
                .order_by(shared_resources.c.created_at.desc())
            )

            if kind:
                query = query.where(shared_resources.c.kind == kind)

            if q:
                from sqlalchemy import or_

                query = query.where(
                    or_(
                        shared_resources.c.name.ilike(f"%{q}%"),
                        shared_resources.c.description.ilike(f"%{q}%"),
                    )
                )

            query = query.limit(limit).offset(offset)

            rows = conn.execute(query)
            return [self._row_to_record(r._mapping) for r in rows]

    def list_resource_versions(
        self, id: str, *, limit: int = 50, offset: int = 0
    ) -> list[SharedResourceRecord]:
        """List all versions of a resource.

        Args:
            id: Resource id.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            List of SharedResourceRecord, all versions.
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                shared_resources.select()
                .where(shared_resources.c.id == id)
                .order_by(shared_resources.c.version.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._row_to_record(r._mapping) for r in rows]

    def activate_resource(self, id: str, version: int) -> SharedResourceRecord:
        """Atomically activate a specific version and deactivate others.

        Args:
            id: Resource id.
            version: Version to activate.

        Returns:
            SharedResourceRecord for the activated version.

        Raises:
            ValueError: If version does not exist.
        """
        target = self.get_resource(id, version)
        if not target:
            raise ValueError(f"Resource {id!r} version {version} not found")

        with self.engine.begin() as conn:
            # Demote all other versions
            conn.execute(
                shared_resources.update()
                .where(shared_resources.c.id == id)
                .values(is_active=0)
            )
            # Activate target version
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

        return self.get_resource(id, version) or target

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_version(self, id: str) -> int:
        """Compute next version number for a resource."""
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(shared_resources.c.version), 0)).where(
                    shared_resources.c.id == id
                )
            ).first()
            return int(row[0]) + 1 if row else 1

    @staticmethod
    def _row_to_record(row: dict | None) -> SharedResourceRecord | None:
        """Convert a row dict to SharedResourceRecord."""
        if not row:
            return None
        # Parse tags from JSON string to tuple
        tags_str = row.get("tags")
        tags: tuple[str, ...] = ()
        if tags_str:
            try:
                tags_list = json.loads(tags_str)
                tags = tuple(tags_list) if isinstance(tags_list, list) else ()
            except json.JSONDecodeError:
                tags = ()

        return SharedResourceRecord(
            id=row["id"],
            version=row["version"],
            kind=row["kind"],
            name=row["name"],
            description=row.get("description"),
            content=row.get("content"),
            config_json=row.get("config_json"),
            sha256=row["sha256"],
            is_active=bool(row.get("is_active", 0)),
            author=row.get("author"),
            changelog=row.get("changelog"),
            tags=tags,
            created_at=row["created_at"],
        )
