"""Workspace tool catalog — the availability surface.

``resolve_workspace_callables`` enumerates every ``CallableItem`` a workspace
has installed, aggregating three source slices (deduped by name):

- MCP tools      → ``resolve_mcp_callables`` (here; reads the tooling.mcp registry)
- Host-env tools → ``resolve_host_env_callables`` (here; reads CAPABILITIES)
- Resources      → ``core/resources/catalog.py``

Answers "what exists", never "who may" — grant∩catalog intersection happens at
dispatch. ponytail: the host-env slice is policy (reads CAPABILITIES + grants);
follow-up 118_02 makes host_env an ordinary MCP server enumerated through the
manifest, at which point this bespoke slice is deleted.
"""

from __future__ import annotations

from agentbox.core.data.constants import McpPolicy
from agentbox.core.db import (
    WorkspaceFileResourceBindingManager,
    WorkspaceHostEnvGrantManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
)
from agentbox.core.resources.catalog import resolve_resource_callables
from agentbox.core.tools.capabilities import CAPABILITIES
from agentbox.core.tools.catalog import CallableItem, enumerate_callables
from agentbox.core.workspaces.tooling.mcp.registry import McpRegistry
from agentbox.core.tools.grants import resolve_grants

__all__ = [
    "resolve_workspace_callables",
    "resolve_host_env_callables",
    "resolve_mcp_callables",
]


def resolve_host_env_callables(
    workspace_id: str,
    host_env_grants: WorkspaceHostEnvGrantManager,
) -> list[CallableItem]:
    """Return CallableItems for host-env capabilities provisioned in *workspace_id*.

    Reads resolved grants via the ``workspace_host_env_grants`` manager and
    cross-references against the canonical ``CAPABILITIES`` registry.

    ponytail: policy code (grants + CAPABILITIES) living in tooling/ — dies in
    118_02 when host_env becomes an ordinary MCP server enumerated through the
    manifest. The host_env_profiles / host_env_call_log table names and MCP
    tool names are wire contracts and stay.
    """
    row = host_env_grants.get_grant(workspace_id)
    if not row:
        effective_grants = resolve_grants(None, None)
    else:
        profile_id = row.get("profile_id")
        profile = (
            host_env_grants.get_profile(profile_id)
            if profile_id is not None
            else None
        )
        effective_grants = resolve_grants(
            profile["grants"] if profile else None, row.get("overrides")
        )

    items: list[CallableItem] = []
    for cap_name, cap_def in CAPABILITIES.items():
        if cap_name in effective_grants or cap_def.default_granted:
            items.append(
                CallableItem(
                    name=str(cap_name),
                    kind="host_env",
                    description=cap_def.description,
                    policy=dict(cap_def.grant_schema),
                )
            )
    return items


def resolve_workspace_callables(
    workspace_id: str,
    host_env_grants: WorkspaceHostEnvGrantManager,
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    mcp_policies: WorkspaceMcpPolicyManager,
    mcp_overrides: WorkspaceMcpOverrideManager,
    mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    mcp_registry: McpRegistry | None = None,
) -> list[CallableItem]:
    """Return every callable item installed in *workspace_id*.

    Gathers the three source slices (MCP, host-env, resources) and
    de-duplicates by name.
    """
    return enumerate_callables([
        resolve_mcp_callables(workspace_id, mcp_policies, mcp_overrides, mcp_tool_overrides, mcp_registry),
        resolve_host_env_callables(workspace_id, host_env_grants),
        resolve_resource_callables(workspace_id, workspace_file_resource_bindings),
    ])


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
