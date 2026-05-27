"""Entry point for the agent_tools stdio MCP server subprocess."""

from agentbox.core.tools.discovery import discover_tools
from agentbox.core.workspace.mcp.servers.agent_tools.server import build_server

discover_tools()
build_server().run(show_banner=False)
