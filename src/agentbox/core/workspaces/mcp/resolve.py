"""Domain helper functions for MCP and host-env grant resolution.

Extracted from WorkspaceService so the execution layer can call these
directly with managers rather than going through a service class.
"""

from __future__ import annotations

from agentbox.core.data.rows import McpServerConfigView

from agentbox.core.db import (
    WorkspaceHostEnvGrantManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
)
from agentbox.core.tools.grants import resolve_grants


def _shallow_merge(
    base: McpServerConfigView | None, overrides: McpServerConfigView | None
) -> McpServerConfigView:
    out: McpServerConfigView = {**(base or {}), **(overrides or {})}
    return out


def resolve_workspace_mcp_helper(
    workspace_mcp_policies: "WorkspaceMcpPolicyManager",
    workspace_mcp_overrides: "WorkspaceMcpOverrideManager",
    workspace_mcp_tool_overrides: "WorkspaceMcpToolOverrideManager",
    workspace_id: str,
    manifest_servers: list[dict],
    *,
    discovered_tools: dict[str, list[str]] | None = None,
) -> dict:
    """Return the workspace's effective MCP server configuration.

    Caller supplies ``manifest_servers`` (project-level MCP server list)
    so this helper has no dependency on ``SystemService``.
    """
    policy = workspace_mcp_policies.get_policy(workspace_id)
    server_overrides = {
        o["server_name"]: o
        for o in workspace_mcp_overrides.list_for_workspace(workspace_id)
    }
    tool_overrides: dict[tuple[str, str], bool] = {}
    for t in workspace_mcp_tool_overrides.list_for_workspace(workspace_id):
        tool_overrides[(t["server_name"], t["tool_name"])] = bool(t["enabled"])

    manifest_by_name = {s["name"]: s for s in manifest_servers}
    all_names = list(manifest_by_name.keys())
    for n in server_overrides:
        if n not in manifest_by_name:
            all_names.append(n)

    out_servers = []
    for name in all_names:
        manifest_entry = manifest_by_name.get(name)
        override = server_overrides.get(name)
        if override is not None:
            enabled = bool(override["enabled"])
        else:
            enabled = policy == "allow_all_unless_disabled"
        base_cfg = manifest_entry.get("config") if manifest_entry else None
        cfg = _shallow_merge(base_cfg, (override or {}).get("config_overrides"))
        disabled_tools: list[str] = []
        if enabled and discovered_tools:
            for tool in discovered_tools.get(name, []):
                flag = tool_overrides.get((name, tool))
                if flag is False:
                    disabled_tools.append(tool)
        source = "override" if override else "default"
        if manifest_entry is None:
            source = "override_only"
        out_servers.append(
            {
                "name": name,
                "enabled": enabled,
                "config": cfg,
                "disabled_tools": disabled_tools,
                "source": source,
            }
        )
    return {"servers": out_servers, "policy": policy}


def resolve_workspace_host_env_helper(
    workspace_host_env_grants: "WorkspaceHostEnvGrantManager",
    workspace_id: str,
) -> dict:
    """Return the workspace's effective host-env grant configuration."""
    row = workspace_host_env_grants.get_grant(workspace_id)
    if not row:
        return {"grants": resolve_grants(None, None), "profile_id": None}
    profile_id = row.get("profile_id")
    profile = (
        workspace_host_env_grants.get_profile(profile_id)
        if profile_id is not None
        else None
    )
    grants = resolve_grants(
        profile["grants"] if profile else None, row.get("overrides")
    )
    return {
        "grants": grants,
        "profile_id": row.get("profile_id"),
        "overrides": row.get("overrides"),
    }


__all__ = ["resolve_workspace_host_env_helper", "resolve_workspace_mcp_helper"]
