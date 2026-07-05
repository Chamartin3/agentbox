"""FastMCP server exposing agentbox runs, prompts, and agent metadata.

This is the MCP **server** surface — distinct from ``agentbox.core.mcp.client``
which is the MCP **client** registry that runners use to discover tools.

Entry point:

    python -m agentbox.mcp          # stdio transport (default)
    python -m agentbox.mcp --http   # streamable-http on $AGENTBOX_MCP_PORT
"""

from agentbox.mcp.server import build_server

__all__ = ["build_server"]
