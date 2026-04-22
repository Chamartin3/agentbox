"""Workspace configuration generation.

Generates Claude Code and OpenCode runner configs per-workspace.
"""

from __future__ import annotations

from .constants import (
    CLAUDE_MCP_PREFIX,
    CLAUDE_TO_OPENCODE_TOOLS,
    DENIED_BUILTIN_TOOLS,
    DISABLED_OPENCODE_AGENTS,
    MCP_SERVER_NAME,
    OPENCODE_MCP_PREFIX,
    OPENCODE_SCHEMA,
    OPENCODE_THEME,
    READ_PREFIXES,
)
from .discovery import AgentDiscovery, DiscoveredAgent
from .generator import ConfigGenerator

__all__ = [
    "CLAUDE_MCP_PREFIX",
    "CLAUDE_TO_OPENCODE_TOOLS",
    "DENIED_BUILTIN_TOOLS",
    "DISABLED_OPENCODE_AGENTS",
    "MCP_SERVER_NAME",
    "OPENCODE_MCP_PREFIX",
    "OPENCODE_SCHEMA",
    "OPENCODE_THEME",
    "READ_PREFIXES",
    "AgentDiscovery",
    "ConfigGenerator",
    "DiscoveredAgent",
]
