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
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
)
from agentbox.core.resources.catalog import resolve_resource_callables
from agentbox.core.tools.builtin import BUILTIN_TOOLS, get_builtin
from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.capabilities import CAPABILITIES
from agentbox.core.tools.catalog import CallableItem, enumerate_callables
from agentbox.core.workspaces.tooling.mcp.registry import McpRegistry

__all__ = [
    "resolve_workspace_callables",
    "resolve_host_env_callables",
    "resolve_mcp_callables",
]


def resolve_host_env_callables() -> list[CallableItem]:
    """Return CallableItems for every host-env capability the server provides.

    Availability only — lists the full ``CAPABILITIES`` taxonomy. Authorization
    is agent territory: the calling agent's grants filter this at dispatch, not
    here. (No workspace grant read — the workspace only owns availability.)
    """
    return [
        CallableItem(
            name=str(cap_name),
            kind="host_env",
            description=cap_def.description,
            policy=dict(cap_def.grant_schema),
        )
        for cap_name, cap_def in CAPABILITIES.items()
    ]


def _declared_tool_callables(declared: list[CanonicalTool] | None) -> list[CallableItem]:
    """The backend's natively-provided tools (highest precedence in the merge)."""
    if not declared:
        return []
    out: list[CallableItem] = []
    for tool in declared:
        spec = get_builtin(tool.value)
        out.append(
            CallableItem(
                name=tool.value,
                kind="builtin",
                description=spec.description if spec else "",
            )
        )
    return out


def _builtin_complement_callables() -> list[CallableItem]:
    """The canonical built-in vocabulary — complements what the adapter / MCP
    servers provide (dedup drops any already surfaced by a higher slice)."""
    return [
        CallableItem(name=s.name.value, kind="builtin", description=s.description)
        for s in BUILTIN_TOOLS
    ]


def resolve_workspace_callables(
    workspace_id: str,
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    mcp_policies: WorkspaceMcpPolicyManager,
    mcp_overrides: WorkspaceMcpOverrideManager,
    mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    mcp_registry: McpRegistry | None = None,
    declared_tools: list[CanonicalTool] | None = None,
) -> list[CallableItem]:
    """Return every callable item available in *workspace_id* — the availability
    surface (what exists), never authorization (who may).

    The merge is precedence-ordered and deduped by name (first wins):
    adapter-declared native tools OVERRIDE the same-named built-in complement;
    MCP-server + host-env + resource tools are additive; the built-in
    vocabulary fills any remaining gaps. Pass *declared_tools* (from the
    selected backend's ``declared_tools()``) to fold in native engine tools.
    """
    return enumerate_callables([
        _declared_tool_callables(declared_tools),
        resolve_mcp_callables(workspace_id, mcp_policies, mcp_overrides, mcp_tool_overrides, mcp_registry),
        resolve_host_env_callables(),
        resolve_resource_callables(workspace_id, workspace_file_resource_bindings),
        _builtin_complement_callables(),
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
