"""Codex backend workspace config — escaped TOML subagent files.

Codex defines project-scoped subagents as TOML files under
``.codex/agents/{name}.toml`` (fields ``name`` / ``description`` /
``developer_instructions``). The values are user prompt text that can
contain quotes, backslashes and newlines, so they're emitted as escaped
TOML basic strings here in code rather than via a text template — the
backend owns its format. Surfaced to the generic generator via
``CodexBackend.build_workspace_items``.

Ref: https://developers.openai.com/codex/subagents
"""

from __future__ import annotations

from agentbox.core.data.workenv import Item, Role, WorkenvConfig


def _toml_basic_string(s: str) -> str:
    """Quote *s* as a TOML basic string, escaping it so any content is valid."""
    out = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{out}"'


def build_codex_items(config: "WorkenvConfig") -> list[Item]:
    """Return one TOML ``Item`` per subagent (routed by the recipe layout)."""
    items: list[Item] = []
    for agent in config.agents:
        if agent.role == "main":
            continue
        content = (
            f"name = {_toml_basic_string(agent.id)}\n"
            f"description = {_toml_basic_string(agent.description)}\n"
            f"developer_instructions = {_toml_basic_string(agent.prompt)}\n"
        )
        items.append(Item(role=Role.subagent, name=agent.id, content=content))
    return items
