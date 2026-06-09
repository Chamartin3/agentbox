"""Render helpers and tool resolution for the Claude Code backend."""

from __future__ import annotations

import json

from agentbox.core.engines.backends.base import HasAgentConfig, RuntimeConfigView


def _runtime_config_view_from_agent(agent: HasAgentConfig) -> RuntimeConfigView:
    """Fallback: read ``allowed_tools`` from the agent's ``_config_json``.

    Needed only when the executor does NOT supply ``runtime_config``
    explicitly (e.g. direct ``render()`` calls in tests).
    """
    raw = getattr(agent, "_config_json", None)
    if raw is None:
        return RuntimeConfigView()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return RuntimeConfigView()
    runtime_section = (raw or {}).get("runtime") if isinstance(raw, dict) else None
    if not isinstance(runtime_section, dict):
        return RuntimeConfigView()
    return RuntimeConfigView(
        allowed_tools=tuple(runtime_section.get("allowed_tools") or ()),
    )


def _intersect_allowed_tools(
    agent_tools: list[str], workspace_tools: list[str] | None
) -> list[str]:
    """Effective allow list = agent ∩ workspace.

    If either side is empty/None, treat it as "no restriction" so the
    other side governs alone.
    """
    if not agent_tools and not workspace_tools:
        return []
    if not agent_tools:
        return list(workspace_tools or [])
    if not workspace_tools:
        return list(agent_tools)
    ws_set = set(workspace_tools)
    return [t for t in agent_tools if t in ws_set]


__all__ = ["_intersect_allowed_tools", "_runtime_config_view_from_agent"]
