"""MCP-source slice of the workspace-tool catalog.

Returns ``list[CallableItem]`` for the MCP servers installed in a
workspace.  The API endpoint and the executor each call this with their
own store + McpRegistry; no HTTP involved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentbox.core.tools.catalog import CallableItem

if TYPE_CHECKING:
    from agentbox.core.workspaces.mcp.client.registry import McpRegistry


def resolve_mcp_callables(
    workspace_id: str,
    store: Any,
    mcp_registry: McpRegistry | None,
) -> list[CallableItem]:
    """Return CallableItems for every enabled, non-disabled MCP tool.

    *store* must have ``resolve_workspace_mcp(workspace_id, manifest_servers)``
    (satisfied by ``SessionStore`` / ``RunStore`` at runtime).

    Stitches ``resolve_workspace_mcp`` (which servers + disabled tools)
    with ``McpToolManifest`` (tool names + descriptions).
    """
    if mcp_registry is None:
        return []

    # Build the manifest-servers list that resolve_workspace_mcp expects.
    manifest_servers: list[dict[str, Any]] = [
        {"name": name, "config": {}}
        for name in mcp_registry.manifest.servers
    ]
    if not manifest_servers:
        return []

    snapshot = store.resolve_workspace_mcp(workspace_id, manifest_servers)
    items: list[CallableItem] = []

    for srv in snapshot.get("servers", []):
        if not srv.get("enabled"):
            continue
        server_name = srv["name"]
        tool_list = mcp_registry.manifest.server_tools(server_name)
        disabled = set(srv.get("disabled_tools", []))
        for t in tool_list:
            if t.name in disabled:
                continue
            items.append(
                CallableItem(
                    name=t.name,
                    kind="mcp",
                    description=t.description,
                    server=server_name,
                    input_schema=t.input_schema,
                )
            )

    return items
