"""Workspaces domain managers — catalog index."""
from __future__ import annotations

from agentbox.core.db.managers.workspaces.workspace import WorkspaceManager
from agentbox.core.db.managers.workspaces.env_doc import WorkspaceEnvDocManager, WorkspaceEnvDocVersionManager
from agentbox.core.db.managers.workspaces.mcp_override import WorkspaceMcpOverrideManager, WorkspaceMcpToolOverrideManager, WorkspaceMcpPolicyManager
from agentbox.core.db.managers.workspaces.host_env_grant import WorkspaceHostEnvGrantManager
from agentbox.core.db.managers.workspaces.runtime_permission import WorkspaceRuntimePermissionManager
from agentbox.core.db.managers.workspaces.subagent import WorkspaceSubagentManager
from agentbox.core.db.managers.workspaces.template import WorkenvTemplateManager

__all__ = [
    "WorkenvTemplateManager",
    "WorkspaceEnvDocManager",
    "WorkspaceEnvDocVersionManager",
    "WorkspaceHostEnvGrantManager",
    "WorkspaceManager",
    "WorkspaceMcpOverrideManager",
    "WorkspaceMcpPolicyManager",
    "WorkspaceMcpToolOverrideManager",
    "WorkspaceRuntimePermissionManager",
    "WorkspaceSubagentManager",
]
