"""Read queries for AgentVersionsMixin."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.schema import (
    active_agent_versions,
    agent_meta,
    agent_version_comments,
    agent_version_files,
    agent_version_ratings,
    agent_versions,
)

logger = logging.getLogger(__name__)


class _AgentVersionsReadMixin:
    """Read-only queries against agent_versions and friends."""

    engine: Engine

    # ------------------------------------------------------------------
    # Version reads
    # ------------------------------------------------------------------

    def latest_version(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select()
                .where(agent_versions.c.agent_id == agent_id)
                .order_by(agent_versions.c.version.desc())
                .limit(1)
            ).first()
            return self._row_dict(row) if row else None

    def get_active_version(self, agent_id: str) -> dict | None:
        """Return the active version pointed at by ``active_agent_versions``.

        Returns ``None`` when no pointer is set — callers either fall
        back to the disk bundle or wait for ``startup_sweep`` to heal
        the missing pointer. Promotion is explicit via
        ``activate_version`` so that the UI/CLI never silently picks a
        version the operator didn't endorse.
        """
        with self.engine.connect() as conn:
            pointer = conn.execute(
                active_agent_versions.select().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            ).first()
            if pointer is None:
                return None
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.id == pointer._mapping["version_id"]
                )
            ).first()
            return self._row_dict(row) if row else None

    def get_version_by_id(self, version_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(agent_versions.c.id == version_id)
            ).first()
            return self._row_dict(row) if row else None

    def get_version(self, agent_id: str, version: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.agent_id == agent_id,
                    agent_versions.c.version == version,
                )
            ).first()
            return self._row_dict(row) if row else None

    def list_versions(self, agent_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_versions.select()
                .where(agent_versions.c.agent_id == agent_id)
                .order_by(agent_versions.c.version.desc())
            )
            return [self._row_dict(r) for r in rows]

    def list_agents_with_latest(self, include_deleted: bool = False) -> list[dict]:
        """Return one row per agent_id — the latest version's snapshot.

        DB-as-source-of-truth read path for the agent list. Avoids hitting
        the filesystem loader so the API surfaces exactly what was imported
        into ``agent_versions`` (including DB-only agents with no on-disk
        bundle).

        Soft-deleted agents (``agent_meta.deleted_at IS NOT NULL``) are
        excluded by default.
        """
        with self.engine.connect() as conn:
            inner = (
                select(
                    agent_versions.c.agent_id,
                    func.max(agent_versions.c.version).label("max_version"),
                )
                .group_by(agent_versions.c.agent_id)
                .subquery()
            )
            q = (
                agent_versions.select()
                .join(
                    inner,
                    (agent_versions.c.agent_id == inner.c.agent_id)
                    & (agent_versions.c.version == inner.c.max_version),
                )
                .order_by(agent_versions.c.created_at.desc())
            )
            rows = list(conn.execute(q))
            if include_deleted:
                return [self._row_dict(r) for r in rows]
            deleted_ids = {
                r._mapping["agent_id"]
                for r in conn.execute(
                    agent_meta.select().where(agent_meta.c.deleted_at.isnot(None))
                )
            }
            return [
                self._row_dict(r)
                for r in rows
                if self._row_dict(r).get("agent_id") not in deleted_ids
            ]

    def get_agent_def(self, agent_id: str):  # -> AgentDef | None
        """Reconstruct an ``AgentDef`` from the latest version's snapshot.

        Returns ``None`` when the agent has never been versioned. Callers
        should prefer this over ``DefinitionLoader.get()`` so runtime
        behavior is driven by the DB, not the filesystem.
        """
        import logging

        from agentbox.core.data.manifest import AgentDef

        log = logging.getLogger(__name__)

        row = self.get_active_version(agent_id) or self.latest_version(agent_id)
        if row is None:
            return None
        if self.is_agent_deleted(agent_id):
            return None
        try:
            return AgentDef.from_db_row(row)
        except ValueError:
            # No config_json or content_snapshot — incomplete row.
            return None
        except Exception as exc:
            log.warning(
                "agent_versions: row for %r v%s failed validation: %s",
                agent_id,
                row.get("version"),
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Version files (read)
    # ------------------------------------------------------------------

    def list_version_files(self, version_id: int) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_version_files.select()
                .where(agent_version_files.c.version_id == version_id)
                .order_by(agent_version_files.c.position, agent_version_files.c.id)
            )
            return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------
    # Agent meta (read)
    # ------------------------------------------------------------------

    def get_agent_meta(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
            return dict(row._mapping) if row else None

    def is_agent_deleted(self, agent_id: str) -> bool:
        meta = self.get_agent_meta(agent_id)
        return bool(meta and meta.get("deleted_at"))

    # ------------------------------------------------------------------
    # Comments (read)
    # ------------------------------------------------------------------

    def get_comment(self, version_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_version_comments.select().where(
                    agent_version_comments.c.version_id == version_id
                )
            ).first()
            return dict(row._mapping) if row else None

    def list_comments(self, version_id: int) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_version_comments.select()
                .where(agent_version_comments.c.version_id == version_id)
                .order_by(agent_version_comments.c.created_at)
            )
            return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------
    # Ratings (read)
    # ------------------------------------------------------------------

    def get_rating(self, version_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_version_ratings.select().where(
                    agent_version_ratings.c.version_id == version_id
                )
            ).first()
            return dict(row._mapping) if row else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_version(self, agent_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(agent_versions.c.version), 0)).where(
                    agent_versions.c.agent_id == agent_id
                )
            ).first()
            return int(row[0]) + 1 if row else 1

    def _get_version_row(self, agent_id: str, version: int) -> dict | None:
        """Low-level: fetch raw version row as dict."""
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_versions.select().where(
                    agent_versions.c.agent_id == agent_id,
                    agent_versions.c.version == version,
                )
            ).first()
            return self._row_dict(row) if row else None

    @staticmethod
    def _row_dict(row: Any) -> dict:
        d = dict(row._mapping)
        d["is_legacy"] = bool(d.get("is_legacy", False))
        return d
