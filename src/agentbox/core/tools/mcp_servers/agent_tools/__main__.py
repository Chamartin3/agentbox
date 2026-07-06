"""Entry point for the agent_tools stdio MCP server subprocess."""

from agentbox.core.tools import discover_tools
from agentbox.core.tools.mcp_servers.agent_tools.server import build_server

discover_tools()
build_server().run(show_banner=False)
