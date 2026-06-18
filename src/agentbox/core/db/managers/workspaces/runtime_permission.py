"""WorkspaceRuntimePermissionManager — runtime permission CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.runtime_permission import WorkspaceRuntimePermission


class WorkspaceRuntimePermissionManager(Manager[WorkspaceRuntimePermission]):
    """Manager for the ``workspace_runtime_permissions`` table."""
    model = WorkspaceRuntimePermission
