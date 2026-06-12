"""Engine config generators — moved from ``core.engines.render``.

Generates per-backend runner config files (agents.json, settings.json,
opencode.json, CLAUDE.md, etc.) into a prepared run directory.

This is the legacy direct generator.  The recipe-driven
:func:`~.generator.render` in the parent package is the canonical path
for new work; see Phase A3 of Plan 046_01 for the convergence plan.
"""

from __future__ import annotations

from .constants import (
    CLAUDE_MCP_PREFIX,
    DENIED_BUILTIN_TOOLS,
    DISABLED_OPENCODE_AGENTS,
    MCP_SERVER_NAME,
    OPENCODE_MCP_PREFIX,
    OPENCODE_SCHEMA,
    OPENCODE_THEME,
    READ_PREFIXES,
)
from .discovery import AgentDiscovery, DiscoveredAgent
from .generator import (
    ConfigGenerator,
    ConfigWriter,
    DEFAULT_WRITERS,
    WriteContext,
    WriteResult,
    make_generator,
)

__all__ = [
    "CLAUDE_MCP_PREFIX",
    "DENIED_BUILTIN_TOOLS",
    "DISABLED_OPENCODE_AGENTS",
    "MCP_SERVER_NAME",
    "OPENCODE_MCP_PREFIX",
    "OPENCODE_SCHEMA",
    "OPENCODE_THEME",
    "READ_PREFIXES",
    "AgentDiscovery",
    "ConfigGenerator",
    "ConfigWriter",
    "DEFAULT_WRITERS",
    "DiscoveredAgent",
    "WriteContext",
    "WriteResult",
    "make_generator",
]
