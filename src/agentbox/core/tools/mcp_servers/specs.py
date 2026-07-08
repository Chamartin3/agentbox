"""Stdio spawn specs for agentbox's own (intrinsic) MCP servers.

These specs are RUN-scoped: their ``env`` carries the resolved grants + run
context (workspace/agent id, workdir, db path), so they're built at execution
time and handed to ``Workspaces.build(into=run_dir, extra_mcp_servers=…)``,
which writes them into the run dir's ``.mcp.json`` alongside every other
server. The engine (Claude/OpenCode) then spawns them and speaks MCP directly.

Both are stdio ``python -m …`` servers. The token backend also builds its
pydantic-ai MCP toolset from ``host_env_server_spec`` — single source of truth
for *how* to spawn each server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agentbox.core.data.payload_types import McpStdioServerSpec


def host_env_server_spec(
    *,
    grants: dict,
    workspace_id: str,
    workdir: Path,
    db_path: Path,
) -> McpStdioServerSpec:
    """Stdio spawn spec (``{command, args, env}``) for the host-env server."""
    return {
        "command": sys.executable,
        "args": ["-m", "agentbox.core.tools.mcp_servers.host_env"],
        "env": {
            "AGENTBOX_HOST_ENV_GRANTS_JSON": json.dumps(grants),
            "AGENTBOX_HOST_ENV_WORKSPACE_ID": workspace_id,
            "AGENTBOX_HOST_ENV_WORKDIR": str(workdir),
            "AGENTBOX_DB_PATH": str(db_path),
        },
    }


def agent_tools_server_spec(
    *,
    grants: set[str],
    agent_id: str,
    workdir: Path,
    db_path: Path,
) -> McpStdioServerSpec:
    """Stdio spawn spec for the agent-tools (shared-tool-registry) server."""
    return {
        "command": sys.executable,
        "args": ["-m", "agentbox.core.tools.mcp_servers.agent_tools"],
        "env": {
            "AGENTBOX_AGENT_TOOLS_GRANTS_JSON": json.dumps(sorted(grants)),
            "AGENTBOX_AGENT_TOOLS_AGENT_ID": agent_id,
            "AGENTBOX_AGENT_TOOLS_RUN_ID": "",
            "AGENTBOX_AGENT_TOOLS_WORKDIR": str(workdir),
            "AGENTBOX_DB_PATH": str(db_path),
        },
    }
