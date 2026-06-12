"""Claude settings.json builder."""

from __future__ import annotations

from agentbox.core.tools import translate_tool

from ._common import _is_read_tool_claude
from .constants import (
    CLAUDE_MCP_PREFIX,
    DENIED_BUILTIN_TOOLS,
    READ_PREFIXES,
)
from .discovery import DiscoveredAgent
from .schemas import ClaudeSettingsConfig


def build_claude_settings(
    agents: list[DiscoveredAgent],
    allowed_builtin: list[str] | None = None,
    mcp_prefix: str = CLAUDE_MCP_PREFIX,
) -> dict[str, dict[str, list[str]]]:
    """Build the Claude Code settings document for a workspace.

    ``allowed_builtin`` lists built-in tools (e.g. ``Read``, ``Glob``,
    ``Grep``) that the workspace explicitly re-enables. Anything in
    ``DENIED_BUILTIN_TOOLS`` but NOT in this list ends up in ``deny``.
    """
    allow: list[str] = []
    seen: set[str] = set()

    for agent in agents:
        for tool in agent["mcp_tools"]:
            translated = translate_tool(tool, "claude_code")
            if translated in seen or not translated.startswith(mcp_prefix):
                continue
            seen.add(translated)

            if _is_read_tool_claude(translated, mcp_prefix):
                allow.append(translated)
            else:
                suffix = translated[len(mcp_prefix):]
                if suffix.endswith("_*"):
                    p = suffix[: -len("_*")]
                    for rp in sorted(READ_PREFIXES):
                        read_key = f"{mcp_prefix}{p}_{rp}"
                        if read_key not in seen:
                            seen.add(read_key)
                            allow.append(read_key)

    allow_builtin = {t for t in (allowed_builtin or []) if isinstance(t, str)}
    deny = sorted(t for t in DENIED_BUILTIN_TOOLS if t not in allow_builtin)
    allow_list = sorted(allow) + sorted(allow_builtin)
    result = {
        "permissions": {
            "allow": allow_list,
            "deny": deny,
        }
    }
    ClaudeSettingsConfig.model_validate(result)
    return result
