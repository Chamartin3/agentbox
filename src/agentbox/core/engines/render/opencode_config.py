"""OpenCode opencode.json builder."""

from __future__ import annotations

from typing import Literal

from ._common import _claude_tool_to_opencode, _is_read_tool_opencode
from .constants import (
    DISABLED_OPENCODE_AGENTS,
    OPENCODE_MCP_PREFIX,
    OPENCODE_SCHEMA,
    OPENCODE_THEME,
)
from .discovery import DiscoveredAgent
from .schemas import OpenCodeConfig

Permission = Literal["allow", "ask"]


def _derive_agent_permissions(oc_tools: list[str]) -> dict[str, Permission]:
    permissions: dict[str, Permission] = {}
    for tool in oc_tools:
        if not tool.startswith(OPENCODE_MCP_PREFIX):
            continue
        if _is_read_tool_opencode(tool):
            permissions.setdefault(tool, "allow")
        else:
            permissions.setdefault(tool, "ask")
            suffix = tool[len(OPENCODE_MCP_PREFIX):]
            if suffix.endswith("_"):
                prefix = suffix[:-1]
                for rp in sorted({"read", "edit", "write", "glob", "grep", "task"}):
                    read_key = f"{OPENCODE_MCP_PREFIX}{prefix}_{rp}"
                    permissions.setdefault(read_key, "allow")
    return permissions


_ALWAYS_ON_MCP_TOOLS = (
    f"{OPENCODE_MCP_PREFIX}skill_list",
    f"{OPENCODE_MCP_PREFIX}skill_get_content",
    f"{OPENCODE_MCP_PREFIX}drafter_list_resources",
    f"{OPENCODE_MCP_PREFIX}drafter_get_resource",
)

_ALWAYS_ON_BUILTIN_TOOLS: dict[str, bool] = {
    "todoread": True,
    "todowrite": True,
}


def _opencode_mcp_entry(
    mcp_url: str | None,
    mcp_transport: str,
    mcp_command: list[str] | None,
) -> dict[str, object]:
    if mcp_url:
        return {"type": "remote", "url": mcp_url, "enabled": True}
    assert mcp_command, "mcp server needs url or command"
    return {"type": "local", "command": mcp_command, "enabled": True}


def build_opencode_config(
    agents: list[DiscoveredAgent],
    mcp_server_name: str,
    mcp_command: list[str] | None,
    mcp_url: str | None = None,
    mcp_transport: str = "http",
    *,
    servers: list[dict] | None = None,
) -> dict[str, object]:
    _always_on_tools = {
        **_ALWAYS_ON_BUILTIN_TOOLS,
        f"{OPENCODE_MCP_PREFIX}skill_list": True,
        f"{OPENCODE_MCP_PREFIX}skill_get_content": True,
        f"{OPENCODE_MCP_PREFIX}drafter_list_resources": True,
        f"{OPENCODE_MCP_PREFIX}drafter_get_resource": True,
    }

    agent_entries: dict[str, dict] = {
        "project_manager": {
            "tools": _always_on_tools.copy(),
            "permission": {"time-server_*": "allow"},
        },
    }

    for agent in agents:
        oc_tools = [_claude_tool_to_opencode(t) for t in agent["mcp_tools"]]
        tools_dict: dict[str, bool] = {
            **_ALWAYS_ON_BUILTIN_TOOLS,
            **dict.fromkeys(oc_tools, True),
        }
        for tool_name in _ALWAYS_ON_MCP_TOOLS:
            tools_dict.setdefault(tool_name, True)
        permissions = _derive_agent_permissions(oc_tools)

        agent_entries[agent["name"]] = {
            "description": agent["description"],
            "prompt": agent["prompt"],
            "tools": tools_dict,
            "permission": permissions,
        }

    for name in DISABLED_OPENCODE_AGENTS:
        agent_entries[name] = {"disable": True}

    global_perms: dict[str, Permission] = {"*": "ask"}
    for agent in agents:
        oc_tools = [_claude_tool_to_opencode(t) for t in agent["mcp_tools"]]
        for tool, perm in _derive_agent_permissions(oc_tools).items():
            global_perms.setdefault(tool, perm)
    for always_allow in _ALWAYS_ON_MCP_TOOLS:
        global_perms[always_allow] = "allow"

    if servers is None:
        servers = [
            {
                "name": mcp_server_name,
                "url": mcp_url,
                "transport": mcp_transport,
                "command": mcp_command,
            }
        ]
    mcp_block: dict[str, object] = {}
    for s in servers:
        mcp_block[s["name"]] = _opencode_mcp_entry(
            s.get("url"), s.get("transport", "http"), s.get("command")
        )
    result = {
        "$schema": OPENCODE_SCHEMA,
        "theme": OPENCODE_THEME,
        "tools": {"skill": False},
        "permission": global_perms,
        "agent": agent_entries,
        "mcp": mcp_block,
    }
    OpenCodeConfig.model_validate(result)
    return result
