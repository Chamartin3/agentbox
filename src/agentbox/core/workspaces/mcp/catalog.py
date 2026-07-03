"""MCP-source slice of the workspace-tool catalog.

Returns ``list[CallableItem]`` for the MCP servers installed in a
workspace.  The API endpoint and the executor each call this with their
own manager instances and McpRegistry; no HTTP involved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.constants import McpPolicy
from agentbox.core.tools.catalog import CallableItem

if TYPE_CHECKING:
    from agentbox.core.db import (
        WorkspaceMcpOverrideManager,
        WorkspaceMcpPolicyManager,
        WorkspaceMcpToolOverrideManager,
    )
    from agentbox.core.workspaces.mcp.client.registry import McpRegistry


def resolve_mcp_callables(
    workspace_id: str,
    mcp_policies: WorkspaceMcpPolicyManager,
    mcp_overrides: WorkspaceMcpOverrideManager,
    mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    mcp_registry: McpRegistry | None,
) -> list[CallableItem]:
    """Return CallableItems for every enabled, non-disabled MCP tool.

    Reads MCP policy, server overrides, and tool overrides from the
    respective managers, then cross-references with ``McpToolManifest``
    (tool names + descriptions).
    """
    if mcp_registry is None:
        return []

    # Build the manifest-servers list.
    manifest_servers: list[dict] = [
        {"name": name, "config": {}}
        for name in mcp_registry.manifest.servers
    ]
    if not manifest_servers:
        return []

    # Resolve MCP policy and overrides from managers.
    policy = mcp_policies.get_policy(workspace_id)
    server_overrides = {
        o["server_name"]: o
        for o in mcp_overrides.list_for_workspace(workspace_id)
    }
    tool_override_map: dict[tuple[str, str], bool] = {}
    for t in mcp_tool_overrides.list_for_workspace(workspace_id):
        tool_override_map[(t["server_name"], t["tool_name"])] = bool(t["enabled"])

    manifest_by_name = {s["name"]: s for s in manifest_servers}
    all_names = list(manifest_by_name.keys())
    for n in server_overrides:
        if n not in manifest_by_name:
            all_names.append(n)

    items: list[CallableItem] = []
    for name in all_names:
        override = server_overrides.get(name)
        if override is not None:
            enabled = bool(override["enabled"])
        else:
            enabled = policy == McpPolicy.ALLOW_ALL_UNLESS_DISABLED

        if not enabled:
            continue

        tool_list = mcp_registry.manifest.server_tools(name)
        disabled = set()
        for t in tool_list:
            flag = tool_override_map.get((name, t.name))
            if flag is False:
                disabled.add(t.name)

        for t in tool_list:
            if t.name in disabled:
                continue
            items.append(
                CallableItem(
                    name=t.name,
                    kind="mcp",
                    description=t.description,
                    server=name,
                    input_schema=t.input_schema,
                )
            )

    return items
