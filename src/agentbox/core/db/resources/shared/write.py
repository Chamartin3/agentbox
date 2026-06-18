"""Write methods for SharedResourcesMixin."""

from __future__ import annotations

import json
from typing import Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Engine

from agentbox.core.db.utils import now_iso
from agentbox.core.db.schema import shared_resources
from agentbox.core.db.resources.shared._models import (
    SharedResourceRecord,
    row_to_record,
)
from agentbox.core.db.resources.shared.hash import _compute_sha256


class _SharedWriteSurface(Protocol):
    """Combined surface for SharedResourceWriteMixin methods that call into
    SharedResourceLookupMixin. Avoids importing the lookup class at runtime."""

    engine: Engine

    def _next_shared_version(self, id: str) -> int: ...
    def get_resource(self, id: str, version: int) -> SharedResourceRecord | None: ...
    def get_active_resource(self, id: str) -> SharedResourceRecord | None: ...


class SharedResourceWriteMixin:
    """Write operations for shared resources. Requires ``self.engine: Engine``."""

    engine: Engine

    def create_resource(
        self: "_SharedWriteSurface",
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
        """Create a new resource (version 1) and optionally activate it."""
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
        result = self.get_resource(id, 1) or row_to_record(
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

    def create_resource_version(
        self: "_SharedWriteSurface",
        id: str,
        *,
        content: str | None = None,
        config_json: str | None = None,
        author: str | None = None,
        changelog: str | None = None,
        activate: bool = False,
        **fields_to_update,
    ) -> SharedResourceRecord:
        """Create a new version of an existing resource."""
        latest = self.get_active_resource(id)
        if not latest and not fields_to_update:
            raise ValueError(f"Resource {id!r} not found and no fields provided")

        next_ver = self._next_shared_version(id)

        kind = fields_to_update.get("kind") or (latest.kind if latest else "")
        name = fields_to_update.get("name") or (latest.name if latest else "")
        description = fields_to_update.get("description") or (
            latest.description if latest else None
        )
        tags = fields_to_update.get("tags") or (latest.tags if latest else None)

        if content is None and config_json is None:
            content = latest.content if latest else None
            config_json = latest.config_json if latest else None

        sha256 = _compute_sha256(content, config_json)
        tags_json = json.dumps(tags) if tags else None

        with self.engine.begin() as conn:
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

        result = self.get_resource(id, next_ver) or row_to_record(
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

    def activate_resource(self: "_SharedWriteSurface", id: str, version: int) -> SharedResourceRecord:
        """Atomically activate a specific version and deactivate others."""
        target = self.get_resource(id, version)
        if not target:
            raise ValueError(f"Resource {id!r} version {version} not found")

        with self.engine.begin() as conn:
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

        return self.get_resource(id, version) or target

    def _next_shared_version(self, id: str) -> int:
        """Compute next version number for a resource."""
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(shared_resources.c.version), 0)).where(
                    shared_resources.c.id == id
                )
            ).first()
            return int(row[0]) + 1 if row else 1
