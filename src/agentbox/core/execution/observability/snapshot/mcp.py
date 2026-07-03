"""Build the immutable MCP snapshot attached to a run row."""

from __future__ import annotations

import logging
from typing import cast

from agentbox.core.data import McpSnapshot
from agentbox.core.db import (
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
)
from agentbox.core.db.system.config import load_project_mcp_servers
from agentbox.core.workspaces.mcp.resolve import resolve_workspace_mcp_helper

logger = logging.getLogger(__name__)


def build_mcp_snapshot(
    workspace_mcp_policies: "WorkspaceMcpPolicyManager",
    workspace_mcp_overrides: "WorkspaceMcpOverrideManager",
    workspace_mcp_tool_overrides: "WorkspaceMcpToolOverrideManager",
    *,
    workspace_id: str | None,
    host_env_grants: dict | None,
) -> McpSnapshot | None:
    """Resolve the workspace's effective MCP server list."""
    if not workspace_id:
        return None
    try:
        manifest_servers = [
            {
                "name": s.name,
                "config": {"url": s.url, "transport": str(s.transport)},
            }
            for s in load_project_mcp_servers()
        ]
        raw = resolve_workspace_mcp_helper(
            workspace_mcp_policies,
            workspace_mcp_overrides,
            workspace_mcp_tool_overrides,
            workspace_id,
            manifest_servers,
        )
        if host_env_grants:
            raw["host_env_grants"] = list(host_env_grants.keys())
            raw["host_env_injected"] = True
        return cast(McpSnapshot, raw)
    except Exception:
        logger.exception(
            "executor: MCP snapshot capture failed for workspace %r",
            workspace_id,
        )
        return None


__all__ = ["build_mcp_snapshot"]
