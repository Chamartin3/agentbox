"""Session CRUD mixin."""

from __future__ import annotations

import warnings

import uuid

from sqlalchemy.engine import Engine

from agentbox.core.db.schema import sessions
from agentbox.core.db.utils import now_iso


class SessionsMixin:
    """Session CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def create_session(self, agent_id: str, mode: str, workdir: str | None) -> str:
        warnings.warn(
            "SessionsMixin.create_session is deprecated; use db.sessions manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
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
        warnings.warn(
            "SessionsMixin.touch_session is deprecated; use db.sessions manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
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
        warnings.warn(
            "SessionsMixin.set_session_workdir is deprecated; use db.sessions manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(workdir=workdir)
            )
