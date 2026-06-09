"""MCP server injection helpers — extracted from RunExecutor."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.engines.render.postrender import (
    inject_agent_tools_mcp as _inject_agent_tools_mcp_helper,
    inject_host_env_mcp as _inject_host_env_mcp_helper,
)


def inject_host_env_mcp(
    run_dir: Path,
    grants: dict,
    workspace_id: str,
    workdir: Path,
    db_path: Path,
) -> None:
    """Inject the host-env MCP server into the run directory."""
    _inject_host_env_mcp_helper(
        run_dir=run_dir,
        grants=grants,
        workspace_id=workspace_id,
        workdir=workdir,
        db_path=db_path,
    )


def inject_agent_tools_mcp(
    run_dir: Path,
    grants: set[str],
    agent_id: str,
    workdir: Path,
    db_path: Path,
) -> None:
    """Inject the agent-tools MCP server into the run directory."""
    _inject_agent_tools_mcp_helper(
        run_dir=run_dir,
        grants=grants,
        agent_id=agent_id,
        workdir=workdir,
        db_path=db_path,
    )
