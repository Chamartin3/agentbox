"""FastMCP server factory + entry point."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.config import SETTINGS
from agentbox.core.tools import discover_tools
from agentbox.mcp.tools import (
    agent_tools,
    agents,
    prompts,
    resources,
    runs,
    feedback,
    time,
)


def build_server() -> FastMCP:
    # Populate the shared agent_tools registry so list_agent_tools sees
    # consumer-registered entry points.
    try:
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
    feedback.register(mcp)
    time.register(mcp)
    resources.register(mcp)
    agent_tools.register(mcp)
    return mcp


def main() -> None:
    transport = SETTINGS.mcp_transport
    mcp = build_server()
    if transport == "http":
        mcp.run(
            transport="streamable-http",
            host=SETTINGS.mcp_host,
            port=SETTINGS.mcp_port,
        )
    else:
        mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
