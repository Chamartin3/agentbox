"""Blob operations mixin for ResourcesMixin."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.engine import Engine

from agentbox.core.data.schema import resource_blobs


class ResourceBlobMixin:
    """Blob read operations. Requires ``self.engine: Engine``."""

    engine: Engine

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
