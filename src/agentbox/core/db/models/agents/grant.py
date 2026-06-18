"""AgentToolGrant model — tool permission grants for agents.

Maps to the ``agent_tool_grants`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index, UniqueConstraint

from agentbox.core.db.base.model import Entity


class AgentToolGrant(Entity, table=True):
    """A tool permission grant (or revocation) for an agent."""

    __tablename__ = tablename("agent_tool_grants")

    id: str = Field(primary_key=True)
    agent_id: str = Field(foreign_key="agents.id", ondelete="CASCADE", nullable=False)
    tool_name: str = Field(nullable=False)
    changelog: str = Field(nullable=False)
    granted_at: str = Field(nullable=False)
    granted_by: Optional[str] = Field(default=None)
    revoked_at: Optional[str] = Field(default=None)
    revoked_by: Optional[str] = Field(default=None)
    revoke_changelog: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        Index("ix_agent_tool_grants_agent", "agent_id"),
        UniqueConstraint("agent_id", "tool_name", name="uq_agent_tool_grant"),
    )
