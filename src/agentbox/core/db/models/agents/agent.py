"""Agent identity models — agent, active_agent_versions, agent_meta.

Maps to the ``agents``, ``active_agent_versions``, and ``agent_meta`` tables.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename
from typing import Optional

from sqlmodel import Field

from agentbox.core.db.base.model import Entity


class Agent(Entity, table=True):
    """Canonical agent identity. Minimal record — metadata lives in ``AgentMeta``."""

    __tablename__ = tablename("agents")

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    created_at: str = Field(nullable=False)


class ActiveAgentVersion(Entity, table=True):
    """Points to the currently active version for each agent."""

    __tablename__ = tablename("active_agent_versions")

    agent_id: str = Field(primary_key=True)
    version_id: int = Field(foreign_key="agent_versions.id", nullable=False)
    activated_at: str = Field(nullable=False)


class AgentMeta(Entity, table=True):
    """Agent metadata — sync mode, source path, lifecycle timestamps."""

    __tablename__ = tablename("agent_meta")

    agent_id: str = Field(primary_key=True)
    sync_mode: str = Field(nullable=False, default="off")
    export_to_disk: int = Field(nullable=False, default=0)
    source_path: Optional[str] = Field(default=None)
    source_format: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)
    deleted_at: Optional[str] = Field(default=None)
    disabled_at: Optional[str] = Field(default=None)


class AgentRunnerProfile(Entity, table=True):
    """Maps an agent to its active runner profile."""

    __tablename__ = tablename("agent_runner_profiles")

    agent_id: str = Field(primary_key=True)
    runner_profile_id: str = Field(foreign_key="runner_profiles.id", nullable=False)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)
