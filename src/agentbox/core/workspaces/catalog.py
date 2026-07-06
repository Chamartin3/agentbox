"""Workspace-tool catalog: gather per-source slices into a single allow-list.

This is the server-side entry point for enumerating every callable item
(``CallableItem``) a workspace has installed.  The API endpoint and the
executor both call through this function; the shape maps directly to the
``GET /api/workspaces/{id}/available_tools`` response.

Each source slice lives in its own domain module:

- MCP tools      → ``core/workspaces/mcp/catalog.py``
- Resources      → ``core/resources/catalog.py``
- Host-env tools → here (will move to ``core/workspaces/guardrails/`` in
  Phase D of plan 069 -- see ``# ponytail:`` on the import chain).
"""

from __future__ import annotations

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
from agentbox.core.workspaces.mcp.catalog import resolve_mcp_callables
from agentbox.core.workspaces.mcp.client.registry import McpRegistry
from agentbox.core.tools.grants import resolve_grants

__all__ = [
    "resolve_workspace_callables",
    "resolve_host_env_callables",
]


def resolve_host_env_callables(
    workspace_id: str,
    host_env_grants: WorkspaceHostEnvGrantManager,
) -> list[CallableItem]:
    """Return CallableItems for host-env capabilities provisioned in *workspace_id*.

    Reads resolved grants via the ``workspace_host_env_grants`` manager and
    cross-references against the canonical ``CAPABILITIES`` registry.

    ``# ponytail:`` This function lives in the workspaces module as a
    temporary home; it will be renamed ``guardrails`` and moved into
    ``core/workspaces/guardrails/catalog.py`` in Phase D of plan 069.
    The host_env_profiles / host_env_call_log table names and MCP tool
    names are wire contracts and stay.
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
