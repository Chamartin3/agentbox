"""environment_mcp — unified internal MCP server.

Exposes the host's native tool surface (fs, shell, git, http, env,
workspace info, web search) to every backend through one FastMCP stdio
server. Each tool is gated by the per-agent ``agent_tool_grants`` set;
nothing else. Tool names are prefixed with ``env.`` so backends see a
single namespace.

Replaces the older host_env + agent_tools split.
"""

from agentbox.core.tools.environment_mcp.server import build_server

__all__ = ["build_server"]
