"""Claude agents.json builder."""

from __future__ import annotations

from .discovery import DiscoveredAgent
from .schemas import ClaudeAgentsConfig


def build_claude_agents(agents: list[DiscoveredAgent]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for agent in agents:
        result[agent["name"]] = {
            "description": agent["description"],
            "prompt": agent["prompt"],
            "allowedTools": agent["mcp_tools"],
        }
    ClaudeAgentsConfig.model_validate(result)
    return result
