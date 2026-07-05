"""Host-environment FastMCP stdio server.

Spawned by the executor as a subprocess when a run's workspace has
host-env grants. Communicates over stdio (MCP protocol).

Usage (executor):
    python -m agentbox.core.mcp.servers.host_env

Required env vars:
    AGENTBOX_HOST_ENV_GRANTS_JSON  — JSON dict of effective grants
    AGENTBOX_HOST_ENV_RUN_ID       — run ID for audit logging
    AGENTBOX_HOST_ENV_WORKSPACE_ID — workspace ID for audit logging
    AGENTBOX_HOST_ENV_WORKDIR      — workdir path
    AGENTBOX_DB_PATH               — SQLite store path for audit log (optional)
"""

from __future__ import annotations

from agentbox.core.data.constants import HOST_ENV_SERVER_NAME
from agentbox.core.mcp.servers.host_env.capabilities import (
    env,
    fs,
    git,
    http,
    shell,
    workspace,
)
from agentbox.core.mcp.servers.host_env.context import HostEnvContext
from fastmcp import FastMCP

_ctx: HostEnvContext | None = None


def _get_ctx() -> HostEnvContext:
    global _ctx
    if _ctx is None:
        _ctx = HostEnvContext.from_env()
    return _ctx


def build_server() -> FastMCP:
    mcp = FastMCP(
        name=HOST_ENV_SERVER_NAME,
        instructions=(
            "Host-environment tools: read/write files, run commands, fetch URLs, "
            "read env vars, and query workspace metadata. Each tool requires a "
            "matching grant from the workspace's host-env policy."
        ),
    )
    fs.register(mcp, _get_ctx)
    shell.register(mcp, _get_ctx)
    git.register(mcp, _get_ctx)
    http.register(mcp, _get_ctx)
    env.register(mcp, _get_ctx)
    workspace.register(mcp, _get_ctx)
    return mcp


def main() -> None:
    mcp = build_server()
    mcp.run()


if __name__ == "__main__":
    main()
