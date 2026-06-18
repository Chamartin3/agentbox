"""Session model — conversation session grouping.

Maps to the ``sessions`` table. Sessions group runs by agent and
conversation mode.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class Session(Entity, table=True):
    """A conversation session that groups multiple runs."""

    __tablename__ = tablename("sessions")

    id: str = Field(primary_key=True)
    agent_id: str = Field(nullable=False)
    mode: str = Field(nullable=False)
    workdir: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)
    last_used_at: Optional[str] = Field(default=None)
