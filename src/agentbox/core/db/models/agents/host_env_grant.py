"""AgentHostEnvGrant model — host-env profile grants per agent.

Maps to the ``agent_host_env_grants`` table. Authorization is agent territory;
the workspace owns only availability.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field

from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.tablename import tablename


class AgentHostEnvGrant(Entity, table=True):
    """A host-env profile linked to an agent with optional overrides."""

    __tablename__ = tablename("agent_host_env_grants")

    agent_id: str = Field(
        primary_key=True, foreign_key="agents.id", ondelete="CASCADE"
    )
    profile_id: Optional[str] = Field(
        foreign_key="host_env_profiles.id", ondelete="SET NULL", default=None,
    )
    overrides: Optional[dict] = Field(default=None, sa_type=JSON)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)
