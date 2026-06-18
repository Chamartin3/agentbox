"""AgentToolGrantManager — tool permission grant CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.grant import AgentToolGrant


class AgentToolGrantManager(Manager[AgentToolGrant]):
    """Manager for the ``agent_tool_grants`` table."""
    model = AgentToolGrant
