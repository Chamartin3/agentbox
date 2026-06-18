"""AgentPromptResourceBinding and WorkspaceFileResourceBinding managers."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.resources.binding import (
    AgentPromptResourceBinding,
    WorkspaceFileResourceBinding,
)


class AgentPromptResourceBindingManager(Manager[AgentPromptResourceBinding]):
    """Manager for the ``agent_prompt_resource_bindings`` table."""
    model = AgentPromptResourceBinding


class WorkspaceFileResourceBindingManager(Manager[WorkspaceFileResourceBinding]):
    """Manager for the ``workspace_file_resource_bindings`` table."""
    model = WorkspaceFileResourceBinding
