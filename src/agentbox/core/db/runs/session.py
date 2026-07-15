"""Session model + manager — conversation session grouping.

Maps to the ``sessions`` table. Sessions group runs by agent and
conversation mode.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional
import uuid
from typing import cast

from sqlmodel import Field

from agentbox.core.db.base.model import Entity
from agentbox.core.data.rows import SessionRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.data._util import now_iso


class Session(Entity, table=True):
    """A conversation session that groups multiple runs."""

    __tablename__ = tablename("sessions")

    id: str = Field(primary_key=True)
    agent_id: str = Field(nullable=False)
    mode: str = Field(nullable=False)
    workdir: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)
    last_used_at: Optional[str] = Field(default=None)


sessions = Session.__table__  # table sourced from the SQLModel entity


class SessionManager(Manager[Session]):
    """Manager for the ``sessions`` table."""

    model = Session

    def create_session(self, agent_id: str, mode: str, workdir: str | None) -> str:
        """Insert a new session row and return its UUID hex id."""
        sid = uuid.uuid4().hex
        self._query(
            sessions.insert().values(
                id=sid,
                agent_id=agent_id,
                mode=mode,
                workdir=workdir,
                created_at=now_iso(),
            )
        )
        return sid

    def touch(self, session_id: str) -> None:
        """Update last_used_at to now for the given session."""
        self._query(
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(last_used_at=now_iso())
        )

    def get_dict(self, session_id: str) -> SessionRow | None:
        """Fetch a session row by id as a typed row, or None."""
        with self._engine.connect() as conn:
            row = conn.execute(
                sessions.select().where(sessions.c.id == session_id)
            ).first()
            return cast(SessionRow, dict(row._mapping)) if row else None

    def set_workdir(self, session_id: str, workdir: str) -> None:
        """Update a session's workdir (executor sets this on first run)."""
        self._query(
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(workdir=workdir)
        )
