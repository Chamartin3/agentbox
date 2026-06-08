"""Session CRUD mixin."""

from __future__ import annotations

import uuid

from sqlalchemy.engine import Engine

from agentbox.core.data.schema import sessions
from agentbox.core.data.utils import now_iso


class SessionsMixin:
    """Session CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def create_session(self, agent_id: str, mode: str, workdir: str | None) -> str:
        sid = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                sessions.insert().values(
                    id=sid,
                    agent_id=agent_id,
                    mode=mode,
                    workdir=workdir,
                    created_at=now_iso(),
                )
            )
        return sid

    def touch_session(self, session_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(last_used_at=now_iso())
            )

    def get_session(self, session_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sessions.select().where(sessions.c.id == session_id)
            ).first()
            return dict(row._mapping) if row else None

    def set_session_workdir(self, session_id: str, workdir: str) -> None:
        """Update a session's workdir. Used by the executor on first run."""
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(workdir=workdir)
            )
