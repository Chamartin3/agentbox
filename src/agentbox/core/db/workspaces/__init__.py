"""Workspaces domain — entities and managers merged per plan 127C.

Maps to the ``workspaces``, ``workspace_env_docs``, ``workspace_env_doc_versions``,
``workspace_mcp_overrides``, ``workspace_mcp_tool_overrides``, ``workspace_mcp_policies``,
``workspace_runtime_permissions``, and ``workspace_subagents`` tables.
"""
from __future__ import annotations

# Entities
from agentbox.core.db.workspaces.workspace import Workspace
from agentbox.core.db.workspaces.env_doc import WorkspaceEnvDoc, WorkspaceEnvDocVersion
from agentbox.core.db.workspaces.mcp_override import (
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
)
from agentbox.core.db.workspaces.runtime_permission import WorkspaceRuntimePermission
from agentbox.core.db.workspaces.subagent import WorkspaceSubagent

# Managers
from agentbox.core.db.workspaces.workspace import WorkspaceManager
from agentbox.core.db.workspaces.env_doc import WorkspaceEnvDocManager, WorkspaceEnvDocVersionManager
from agentbox.core.db.workspaces.mcp_override import (
    WorkspaceMcpOverrideManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceMcpPolicyManager,
)
from agentbox.core.db.workspaces.runtime_permission import WorkspaceRuntimePermissionManager
from agentbox.core.db.workspaces.subagent import WorkspaceSubagentManager
from agentbox.core.db.workspaces.read import WorkspaceReadManager

__all__ = [
    # entities
    "Workspace",
    "WorkspaceEnvDoc",
    "WorkspaceEnvDocVersion",
    "WorkspaceMcpOverride",
    "WorkspaceMcpPolicy",
    "WorkspaceMcpToolOverride",
    "WorkspaceRuntimePermission",
    "WorkspaceSubagent",
    # managers
    "WorkspaceManager",
    "WorkspaceEnvDocManager",
    "WorkspaceEnvDocVersionManager",
    "WorkspaceMcpOverrideManager",
    "WorkspaceMcpToolOverrideManager",
    "WorkspaceMcpPolicyManager",
    "WorkspaceRuntimePermissionManager",
    "WorkspaceSubagentManager",
    "WorkspaceReadManager",
]
