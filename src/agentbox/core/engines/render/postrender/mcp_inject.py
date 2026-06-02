"""Pure helpers that patch ``claude_mcp.json`` to add agentbox MCP servers.

Extracted from ``RunExecutor._inject_*`` so the executor no longer owns
the on-disk MCP-config format. Backends call these from their
``post_render`` hook (the :class:`BackendAdapter` default does so).

Both functions are idempotent at the entry level — re-running them
replaces the previous entry under the same server name. They never
delete or rewrite other ``mcpServers`` entries.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_mcp(run_dir: Path) -> tuple[Path, dict]:
    mcp_path = run_dir / "claude_mcp.json"
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
    """Add the agentbox host-env stdio MCP server to ``claude_mcp.json``.

    Claude Code / OpenCode spawn the server themselves when they see it
    in the MCP config. The effective grants + run context flow via env
    vars so the server process can enforce them and write to the audit
    log.
    """
    mcp_path, mcp_data = _load_mcp(run_dir)
    mcp_data["mcpServers"]["agentbox-host-env"] = {
        "command": sys.executable,
        "args": ["-m", "agentbox.core.workspace.mcp.servers.host_env"],
        "env": {
            "AGENTBOX_HOST_ENV_GRANTS_JSON": json.dumps(grants),
            "AGENTBOX_HOST_ENV_WORKSPACE_ID": workspace_id,
            "AGENTBOX_HOST_ENV_WORKDIR": str(workdir),
            "AGENTBOX_DB_PATH": str(db_path),
        },
    }
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
    """Add the agentbox agent-tools stdio MCP server to ``claude_mcp.json``."""
    mcp_path, mcp_data = _load_mcp(run_dir)
    mcp_data["mcpServers"]["agentbox-agent-tools"] = {
        "command": sys.executable,
        "args": ["-m", "agentbox.core.workspace.mcp.servers.agent_tools"],
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
