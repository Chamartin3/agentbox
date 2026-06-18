"""WorkspaceSubagentManager — subagent registration CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.subagent import WorkspaceSubagent


class WorkspaceSubagentManager(Manager[WorkspaceSubagent]):
    """Manager for the ``workspace_subagents`` table."""
    model = WorkspaceSubagent
