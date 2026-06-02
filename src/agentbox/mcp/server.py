"""FastMCP server factory + entry point."""

from __future__ import annotations

import os

from fastmcp import FastMCP

from agentbox.mcp.tools import (
    agent_tools,
    agents,
    prompts,
    resources,
    runs,
    stats,
    time,
)


def build_server() -> FastMCP:
    # Populate the shared agent_tools registry so list_agent_tools sees
    # consumer-registered entry points.
    try:
        from agentbox.core.tools import discover_tools

        discover_tools()
    except Exception:
        pass

    mcp = FastMCP(
        name="agentbox",
        instructions=(
            "Inspect agentbox runs and manage versioned system prompts. "
            "Every prompt edit bumps the version and requires a non-empty "
            "`reason` (stored as the version's changelog)."
        ),
    )
    runs.register(mcp)
    prompts.register(mcp)
    agents.register(mcp)
    stats.register(mcp)
    time.register(mcp)
    resources.register(mcp)
    agent_tools.register(mcp)
    return mcp


def main() -> None:
    transport = os.environ.get("AGENTBOX_MCP_TRANSPORT", "stdio")
    mcp = build_server()
    if transport == "http":
        host = os.environ.get("AGENTBOX_MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("AGENTBOX_MCP_PORT", "8766"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
