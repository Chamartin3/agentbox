"""Version lifecycle mixin for ResourcesMixin."""

from __future__ import annotations

import json
import uuid
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from agentbox.core.constants import ImportSource
from agentbox.core.data.utils import now_iso
from agentbox.core.data.row_types import RepoResourceRow
from agentbox.core.data.schema import (
    active_resource_versions,
    resource_blobs,
    resource_versions,
    resources as resources_table,
)
from agentbox.core.data.resources.crud._helpers import (
    _hash_blobs,
    _validate_changelog,
)


class _VersionImportSurface(Protocol):
    """Combined surface for import_repo_version / rollback_repo_resource:
    own mixin methods + get_repo_resource from ResourceCrudMixin.
    Pyright cannot see through MRO; this Protocol bridges the gap."""

    engine: Engine

    def get_repo_resource(self, resource_id: str) -> RepoResourceRow | None: ...
    def get_repo_version(self, version_id: str) -> dict | None: ...
    def _next_version_number(self, resource_id: str) -> int: ...
    def _activate_version_in_conn(
        self,
        conn: object,
        resource_id: str,
        version_id: str,
        *,
        activated_by: str | None,
    ) -> None: ...
    def import_repo_version(
        self,
        resource_id: str,
        blobs: list[tuple[str, bytes, str | None, str | None]],
        *,
        import_source: str,
        changelog: str,
        source_metadata: dict | None = ...,
        metadata: dict | None = ...,
        draft: bool = ...,
        created_by: str | None = ...,
        activate: bool = ...,
    ) -> dict: ...


class ResourceVersionMixin:
    """Version lifecycle operations. Requires ``self.engine: Engine``."""

    engine: Engine

    def _next_version_number(self, resource_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(
                    func.coalesce(func.max(resource_versions.c.version_number), 0)
                ).where(resource_versions.c.resource_id == resource_id)
            ).first()
        return int(row[0]) + 1 if row else 1

    def import_repo_version(
        self: "_VersionImportSurface",
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
        """Create a new resource version."""
        ImportSource.coerce(import_source, label="import_source")
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
        self: "_VersionImportSurface",
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


class CrudVersionSurface(Protocol):
    """Type-only view of ResourceVersionMixin for sibling-mixin self-binding."""

    def get_active_repo_version(self, resource_id: str) -> dict | None: ...
