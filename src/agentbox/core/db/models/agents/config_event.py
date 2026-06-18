"""AgentConfigEvent model — configuration change tracking for agents.

Maps to the ``agent_config_events`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class AgentConfigEvent(Entity, table=True):
    """Audit log of configuration changes to an agent definition."""

    __tablename__ = tablename("agent_config_events")

    id: int = Field(default=None, primary_key=True)
    agent_id: str = Field(nullable=False)
    field: str = Field(nullable=False)
    from_value: Optional[str] = Field(default=None)
    to_value: Optional[str] = Field(default=None)
    author: str = Field(nullable=False)
    source: str = Field(nullable=False)
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        Index("ix_agent_config_events_agent", "agent_id"),
        Index("ix_agent_config_events_created", "created_at"),
    )
