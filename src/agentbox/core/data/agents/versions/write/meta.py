"""Agent-meta writes + comment/rating writes."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from agentbox.core.data.agents.versions.read import _AgentVersionsReadMixin
from agentbox.core.data.utils import now_iso
from agentbox.core.data.schema import (
    active_agent_versions,
    agent_meta,
    agent_version_comments,
    agent_version_ratings,
)


class _AgentVersionsMetaMixin(_AgentVersionsReadMixin):
    """Mutations against agent_meta, agent_version_comments, agent_version_ratings."""

    engine: Engine

    def init_agent_meta(
        self,
        agent_id: str,
        sync_mode: str = "off",
        export_to_disk: bool = False,
        source_path: str | None = None,
        source_format: str | None = None,
    ) -> dict:
        existing = self.get_agent_meta(agent_id)
        now = now_iso()
        if existing is not None:
            return existing
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.insert().values(
                    agent_id=agent_id,
                    sync_mode=sync_mode,
                    export_to_disk=int(export_to_disk),
                    source_path=source_path,
                    source_format=source_format,
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.get_agent_meta(agent_id) or {}

    def update_agent_meta(
        self,
        agent_id: str,
        sync_mode: str | None = None,
        export_to_disk: bool | None = None,
        source_path: str | None = None,
        source_format: str | None = None,
    ) -> dict | None:
        """Update agent_meta fields. Only supplied fields are changed."""
        existing = self.get_agent_meta(agent_id)
        if existing is None:
            return None
        now = now_iso()
        values: dict[str, object] = {"updated_at": now}
        if sync_mode is not None:
            values["sync_mode"] = sync_mode
        if export_to_disk is not None:
            values["export_to_disk"] = int(export_to_disk)
        if source_path is not None:
            values["source_path"] = source_path
        if source_format is not None:
            values["source_format"] = source_format
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.update()
                .where(agent_meta.c.agent_id == agent_id)
                .values(**values)
            )
        return self.get_agent_meta(agent_id)

    def soft_delete_agent(self, agent_id: str) -> dict | None:
        """Mark an agent as deleted by stamping ``agent_meta.deleted_at``.

        Idempotent: returns the current meta row whether or not the agent
        was already deleted. Returns ``None`` if the agent has no version
        history at all.
        """
        latest = self.latest_version(agent_id)
        if latest is None:
            return None
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
            if existing:
                conn.execute(
                    agent_meta.update()
                    .where(agent_meta.c.agent_id == agent_id)
                    .values(deleted_at=now, updated_at=now)
                )
            else:
                conn.execute(
                    agent_meta.insert().values(
                        agent_id=agent_id,
                        sync_mode="off",
                        export_to_disk=0,
                        source_path=None,
                        source_format=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=now,
                    )
                )
            conn.execute(
                active_agent_versions.delete().where(
                    active_agent_versions.c.agent_id == agent_id
                )
            )
        return self.get_agent_meta(agent_id)

    def restore_agent(self, agent_id: str) -> dict | None:
        """Clear ``deleted_at``. Active version pointer must be re-set
        separately if the caller wants the agent runnable again."""
        meta = self.get_agent_meta(agent_id)
        if meta is None:
            return None
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.update()
                .where(agent_meta.c.agent_id == agent_id)
                .values(deleted_at=None, updated_at=now_iso())
            )
        return self.get_agent_meta(agent_id)

    def disable_agent(self, agent_id: str) -> dict | None:
        """Stamp ``agent_meta.disabled_at``. Visible but un-invokable.

        Idempotent: returns the current meta row whether or not the agent
        was already disabled. Returns ``None`` if the agent has no version
        history at all. Does NOT clear the active version pointer — the
        agent is still "configured", just gated at dispatch.
        """
        latest = self.latest_version(agent_id)
        if latest is None:
            return None
        now = now_iso()
        with self.engine.begin() as conn:
            existing = conn.execute(
                agent_meta.select().where(agent_meta.c.agent_id == agent_id)
            ).first()
            if existing:
                conn.execute(
                    agent_meta.update()
                    .where(agent_meta.c.agent_id == agent_id)
                    .values(disabled_at=now, updated_at=now)
                )
            else:
                conn.execute(
                    agent_meta.insert().values(
                        agent_id=agent_id,
                        sync_mode="off",
                        export_to_disk=0,
                        source_path=None,
                        source_format=None,
                        created_at=now,
                        updated_at=now,
                        disabled_at=now,
                    )
                )
        return self.get_agent_meta(agent_id) or {}

    def enable_agent(self, agent_id: str) -> dict | None:
        """Clear ``disabled_at``."""
        meta = self.get_agent_meta(agent_id)
        if meta is None:
            return None
        with self.engine.begin() as conn:
            conn.execute(
                agent_meta.update()
                .where(agent_meta.c.agent_id == agent_id)
                .values(disabled_at=None, updated_at=now_iso())
            )
        return self.get_agent_meta(agent_id)

    def add_comment(self, version_id: int, author: str, body: str) -> dict:
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_comments.insert().values(
                    version_id=version_id,
                    author=author,
                    body=body,
                    created_at=now_iso(),
                )
            )
        comment = self.get_comment(version_id)
        assert comment is not None
        return comment

    def set_rating(self, version_id: int, rating: int, rater: str) -> dict:
        if not (1 <= rating <= 5):
            raise ValueError(f"rating must be 1-5, got {rating}")
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_ratings.insert().values(
                    version_id=version_id,
                    rating=rating,
                    rater=rater,
                    rated_at=now_iso(),
                )
            )
        return self.get_rating(version_id) or {}
