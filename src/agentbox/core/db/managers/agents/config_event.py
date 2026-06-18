"""AgentConfigEventManager — agent configuration change audit log CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.config_event import AgentConfigEvent


class AgentConfigEventManager(Manager[AgentConfigEvent]):
    """Manager for the ``agent_config_events`` table."""
    model = AgentConfigEvent
