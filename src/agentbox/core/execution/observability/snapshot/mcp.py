"""Build the immutable MCP snapshot attached to a run row."""

from __future__ import annotations

import logging

from agentbox.core.db import McpSnapshot, SnapshotStore
from agentbox.core.db.system.config import load_project_mcp_servers

logger = logging.getLogger(__name__)


def build_mcp_snapshot(
    store: SnapshotStore,
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
        snapshot = store.resolve_workspace_mcp(
            workspace_id, manifest_servers
        )
        if host_env_grants:
            snapshot["host_env_grants"] = list(host_env_grants.keys())
            snapshot["host_env_injected"] = True
        return snapshot
    except Exception:
        logger.exception(
            "executor: MCP snapshot capture failed for workspace %r",
            workspace_id,
        )
        return None


__all__ = ["build_mcp_snapshot"]
