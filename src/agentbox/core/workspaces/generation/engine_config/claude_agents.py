"""Claude agents.json builder."""

from __future__ import annotations

from agentbox.core.tools import translate_tool

from .discovery import DiscoveredAgent
from .schemas import ClaudeAgentsConfig


def build_claude_agents(agents: list[DiscoveredAgent]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for agent in agents:
        allowed_tools = [
            translate_tool(t, "claude_code")
            for t in agent["mcp_tools"]
        ]
        result[agent["name"]] = {
            "description": agent["description"],
            "prompt": agent["prompt"],
            "allowedTools": allowed_tools,
        }
    ClaudeAgentsConfig.model_validate(result)
    return result
