"""Agent-versions write operations (composite of task-based sub-mixins)."""

from __future__ import annotations

from agentbox.core.data.agents.versions.write.create import _AgentVersionsAgentMixin
from agentbox.core.data.agents.versions.write.files import _AgentVersionsFilesMixin
from agentbox.core.data.agents.versions.write.meta import _AgentVersionsMetaMixin
from agentbox.core.data.agents.versions.write.revisions import _AgentVersionsRevisionsMixin


class AgentWriteMixin(
    _AgentVersionsAgentMixin,
    _AgentVersionsRevisionsMixin,
    _AgentVersionsFilesMixin,
    _AgentVersionsMetaMixin,
):
    """All agent-version write operations."""
