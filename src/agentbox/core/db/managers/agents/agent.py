"""Agent, ActiveAgentVersion, AgentMeta and AgentRunnerProfile managers."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.agent import (
    ActiveAgentVersion,
    Agent,
    AgentMeta,
    AgentRunnerProfile,
)


class AgentManager(Manager[Agent]):
    """Manager for the ``agents`` table."""
    model = Agent


class ActiveAgentVersionManager(Manager[ActiveAgentVersion]):
    """Manager for the ``active_agent_versions`` table."""
    model = ActiveAgentVersion


class AgentMetaManager(Manager[AgentMeta]):
    """Manager for the ``agent_meta`` table."""
    model = AgentMeta


class AgentRunnerProfileManager(Manager[AgentRunnerProfile]):
    """Manager for the ``agent_runner_profiles`` table."""
    model = AgentRunnerProfile
