"""Configuration generation constants.

Per-backend native tool names and translations are derived from the
shared taxonomy in ``agentbox.core.tools.translation``.
"""

from __future__ import annotations

from agentbox.core.tools.translation import NATIVE_TOOL_NAMES as _NATIVE_TOOL_NAMES

_CLD_NATIVE = _NATIVE_TOOL_NAMES["claude_code"]

# Read-only tool action prefixes — tools matching these are auto-allowed
READ_PREFIXES: frozenset[str] = frozenset(
    {"list_", "get_", "search_", "check_", "select_", "find_"}
)

# Default MCP server name (override via agentbox.toml ``mcp_server_name``).
MCP_SERVER_NAME = "mcp"

# Prefix for Claude Code MCP tool references (mcp__<server>__<tool>)
CLAUDE_MCP_PREFIX = f"mcp__{MCP_SERVER_NAME}__"

# Prefix for OpenCode MCP tool references (<server>_<tool>)
OPENCODE_MCP_PREFIX = f"{MCP_SERVER_NAME}_"

# Built-in tools denied by default in the Claude Code MCP-only environment.
# Derived from the Claude Code backend's native tool names — every native
# name is denied unless the workspace explicitly allowlists it.
DENIED_BUILTIN_TOOLS: tuple[str, ...] = tuple(sorted(_CLD_NATIVE.values()))

# OpenCode built-in agents to disable (we use MCP-only, not their agents)
DISABLED_OPENCODE_AGENTS = ("build", "plan", "general", "explore", "diagnose")

# OpenCode schema URL
OPENCODE_SCHEMA = "https://opencode.ai/config.json"

# Default OpenCode theme
OPENCODE_THEME = "dracula"
