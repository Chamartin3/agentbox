"""Workspace MCP override managers."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.workspaces.mcp_override import (
    WorkspaceMcpOverride,
    WorkspaceMcpPolicy,
    WorkspaceMcpToolOverride,
)


class WorkspaceMcpOverrideManager(Manager[WorkspaceMcpOverride]):
    """Manager for the ``workspace_mcp_overrides`` table."""
    model = WorkspaceMcpOverride


class WorkspaceMcpToolOverrideManager(Manager[WorkspaceMcpToolOverride]):
    """Manager for the ``workspace_mcp_tool_overrides`` table."""
    model = WorkspaceMcpToolOverride


class WorkspaceMcpPolicyManager(Manager[WorkspaceMcpPolicy]):
    """Manager for the ``workspace_mcp_policies`` table."""
    model = WorkspaceMcpPolicy
