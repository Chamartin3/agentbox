"""OpenCode workspace config generation.

Builds ``opencode.json`` — the engine-shaped config blob (schema, theme,
agent table, MCP servers). This is logic a ``recipe.yaml`` can't express,
so it lives here in the backend that owns the OpenCode format and is
surfaced to the generic generator via ``OpenCodeBackend.build_workspace_items``.
"""

from __future__ import annotations

import json

from agentbox.core.engines.backends.opencode.schema import (
    AgentEntry,
    McpLocal,
    McpRemote,
    OpenCodeConfig,
)
from agentbox.core.workspaces.generation.config import McpRef, WorkenvConfig
from agentbox.core.workspaces.generation.payload import Item, Role


def build_opencode_items(config: WorkenvConfig) -> list[Item]:
    """Return the ``opencode.json`` Item for *config* (placed via recipe layout)."""
    oc = OpenCodeConfig(
        tools={"skill": True},
        permission={"*": "allow"},
        agent={a.id: AgentEntry() for a in config.agents if a.role == "main"},
        mcp=_mcp_entries(config.mcp_servers),
    )
    content = json.dumps(oc.model_dump(by_alias=True), indent=2) + "\n"
    return [Item(role=Role.engine_config, name=config.name, content=content)]


def _mcp_entries(servers: list[McpRef]) -> dict[str, McpRemote | McpLocal]:
    entries: dict[str, McpRemote | McpLocal] = {}
    for srv in servers:
        if not isinstance(srv, McpRef):
            continue
        url = srv.config.get("url")
        command = srv.config.get("command")
        transport = srv.config.get("transport", "stdio")
        if url:
            entries[srv.name] = McpRemote(
                type="remote" if transport == "http" else transport, url=url
            )
        elif command:
            entries[srv.name] = McpLocal(command=command)
    return entries
