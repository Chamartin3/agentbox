"""Patch a run dir's native MCP config to add agentbox's own MCP servers.

The executor calls these after the recipe renders the run dir, to wire in
the per-run host-env and agent-tools stdio servers (with their grants in
env vars). They patch Claude's native ``.mcp.json`` — the file Claude
discovers from the run cwd. OpenCode's ``opencode.json`` carries no env
field for stdio servers, so OpenCode injection is intentionally not done
here (parity with the prior behavior, where inject only ever touched
Claude's MCP file).

Both functions are idempotent at the entry level — re-running replaces the
entry under the same server name and never touches other ``mcpServers``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from agentbox.core.data.constants import AGENT_TOOLS_SERVER_NAME, HOST_ENV_SERVER_NAME, MCP_FILENAME
from agentbox.core.data.payload_types import McpStdioServerSpec

logger = logging.getLogger(__name__)


def host_env_server_spec(
    *,
    grants: dict,
    workspace_id: str,
    workdir: Path,
    db_path: Path,
) -> McpStdioServerSpec:
    """Return the stdio MCP server spec (``{command, args, env}``) for host-env.

    Single source of truth for *how* to spawn the host-env server: both the
    .mcp.json injection (MCP-aware backends) and the token backend's pydantic-ai
    MCP toolset build their connection from this.
    """
    spec: McpStdioServerSpec = {
        "command": sys.executable,
        "args": ["-m", "agentbox.core.tools.mcp_servers.host_env"],
        "env": {
            "AGENTBOX_HOST_ENV_GRANTS_JSON": json.dumps(grants),
            "AGENTBOX_HOST_ENV_WORKSPACE_ID": workspace_id,
            "AGENTBOX_HOST_ENV_WORKDIR": str(workdir),
            "AGENTBOX_DB_PATH": str(db_path),
        },
    }
    return spec


def _load_mcp(run_dir: Path) -> tuple[Path, dict]:
    mcp_path = run_dir / MCP_FILENAME
    if mcp_path.exists():
        data = json.loads(mcp_path.read_text())
    else:
        data = {"mcpServers": {}}
    data.setdefault("mcpServers", {})
    return mcp_path, data


def _write_mcp(mcp_path: Path, data: dict) -> None:
    mcp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def inject_host_env_mcp(
    *,
    run_dir: Path,
    grants: dict,
    workspace_id: str,
    workdir: Path,
    db_path: Path,
) -> None:
    """Add the agentbox host-env stdio MCP server to ``.mcp.json``.

    Claude spawns the server itself when it sees it in the MCP config. The
    effective grants + run context flow via env vars so the server process
    can enforce them and write to the audit log.
    """
    mcp_path, mcp_data = _load_mcp(run_dir)
    mcp_data["mcpServers"][HOST_ENV_SERVER_NAME] = host_env_server_spec(
        grants=grants, workspace_id=workspace_id, workdir=workdir, db_path=db_path
    )
    _write_mcp(mcp_path, mcp_data)
    logger.debug(
        "post_render: injected host-env MCP server for workspace %r with caps: %s",
        workspace_id,
        list(grants.keys()),
    )


def inject_agent_tools_mcp(
    *,
    run_dir: Path,
    grants: set[str],
    agent_id: str,
    workdir: Path,
    db_path: Path,
) -> None:
    """Add the agentbox agent-tools stdio MCP server to ``.mcp.json``."""
    mcp_path, mcp_data = _load_mcp(run_dir)
    mcp_data["mcpServers"][AGENT_TOOLS_SERVER_NAME] = {
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
    _write_mcp(mcp_path, mcp_data)
    logger.debug(
        "post_render: injected agent-tools MCP server for agent %r with tools: %s",
        agent_id,
        sorted(grants),
    )
