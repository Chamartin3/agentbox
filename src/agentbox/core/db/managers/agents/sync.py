"""AgentSyncManager — manifest-to-DB sync metadata CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.agents.sync import AgentSync


class AgentSyncManager(Manager[AgentSync]):
    """Manager for the ``agent_sync`` table."""
    model = AgentSync
