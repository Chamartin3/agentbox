"""Configuration generation constants.

Ported from bin/constants.py — these are the constants used by the
Claude Code and OpenCode config generators.
"""

from __future__ import annotations

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

# Built-in code tools to deny in the MCP-only environment.
DENIED_BUILTIN_TOOLS: tuple[str, ...] = (
    "Bash",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Glob",
    "Grep",
    "NotebookEdit",
)

# Claude Code ↔ OpenCode tool name mapping
CLAUDE_TO_OPENCODE_TOOLS: dict[str, str] = {
    "AskUserQuestion": "question",
    "Task": "task",
    "WebFetch": "webfetch",
    "WebSearch": "websearch",
}

# OpenCode built-in agents to disable (we use MCP-only, not their agents)
DISABLED_OPENCODE_AGENTS = ("build", "plan", "general", "explore", "diagnose")

# OpenCode schema URL
OPENCODE_SCHEMA = "https://opencode.ai/config.json"

# Default OpenCode theme
OPENCODE_THEME = "dracula"
