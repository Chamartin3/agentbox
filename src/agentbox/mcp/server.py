"""FastMCP server factory + entry point."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.core.config import SETTINGS
from agentbox.core.tools import discover_tools
from agentbox.mcp.context import get_mcp_context
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
    ctx = get_mcp_context()

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
    runs.register(mcp, ctx)
    prompts.register(mcp, ctx)
    agents.register(mcp, ctx)
    feedback.register(mcp, ctx)
    time.register(mcp, ctx)
    resources.register(mcp, ctx)
    agent_tools.register(mcp, ctx)
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
