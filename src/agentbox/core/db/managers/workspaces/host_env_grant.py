"""WorkspaceHostEnvGrantManager — host env grant CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.host_env_grant import WorkspaceHostEnvGrant


class WorkspaceHostEnvGrantManager(Manager[WorkspaceHostEnvGrant]):
    """Manager for the ``workspace_host_env_grants`` table."""
    model = WorkspaceHostEnvGrant
