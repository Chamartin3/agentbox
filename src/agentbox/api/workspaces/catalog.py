"""Workspace-scoped availability catalog (Plan 062_01).

``GET /api/workspaces/{workspace_id}/available_tools`` returns the
union of everything the workspace has *installed* — MCP-server tools,
host-environment capabilities, and resource bindings — expressed in
canonical vocabulary where applicable.

This is the pick-list the agent's authorization surface draws from;
it is **not** a global taxonomy reference (that remains
``/api/agent_tools``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from agentbox.api.deps import get_mcp_registry, get_store
from agentbox.core.service import SessionStore
from agentbox.core.tools import CAPABILITIES
from agentbox.core.workspaces.mcp.client.registry import McpRegistry

router = APIRouter(tags=["workspace-catalog"])


def _resolve_mcp_tools(
    workspace_id: str,
    store: SessionStore,
    mcp_registry: McpRegistry,
) -> list[dict]:
    """Return MCP tools available in *workspace_id*.

    Stitches together the ``McpSnapshot`` (which servers/tools are
    enabled) with the ``McpToolManifest`` (tool names + descriptions).
    """
    manifest_servers: list[dict] = []
    for srv_name in mcp_registry.manifest.servers:
        manifest_servers.append({"name": srv_name, "config": {}})

    snapshot = store.resolve_workspace_mcp(workspace_id, manifest_servers or [])
    tools: list[dict] = []

    for srv in snapshot.get("servers", []):
        if not srv.get("enabled"):
            continue
        server_name = srv["name"]
        tool_list = mcp_registry.manifest.server_tools(server_name)
        disabled = set(srv.get("disabled_tools", []))
        for t in tool_list:
            if t.name in disabled:
                continue
            tools.append({
                "name": t.name,
                "description": t.description,
                "kind": "mcp",
                "server": server_name,
                "input_schema": t.input_schema,
            })

    return tools


def _resolve_host_env_tools(
    workspace_id: str,
    store: SessionStore,
) -> list[dict]:
    """Return host-env capabilities provisioned in *workspace_id*."""
    resolved = store.resolve_workspace_host_env(workspace_id)
    grants = resolved.get("grants", {}) if isinstance(resolved, dict) else {}

    tools: list[dict] = []
    for cap_name, cap_def in CAPABILITIES.items():
        if cap_name in grants or cap_def.default_granted:
            tools.append({
                "name": cap_name,
                "description": cap_def.description,
                "kind": "host_env",
                "grant_schema": cap_def.grant_schema,
            })
    return tools


def _resolve_resource_bindings(
    workspace_id: str,
    store: SessionStore,
) -> list[dict]:
    """Return resource bindings available in *workspace_id*."""
    bindings = store.list_workspace_file_bindings(workspace_id)
    return [
        {
            "name": b.get("target_path", b.get("resource_id", "")),
            "description": f"Resource binding: {b.get('resource_id', '')}",
            "kind": "resource",
            "resource_id": b.get("resource_id", ""),
            "target_path": b.get("target_path", ""),
        }
        for b in bindings
    ]


@router.get("/api/workspaces/{workspace_id}/available_tools")
def list_available_tools(
    workspace_id: str,
    store: Annotated[SessionStore, Depends(get_store)],
    mcp_registry: Annotated[McpRegistry, Depends(get_mcp_registry)],
):
    """Return every tool, capability, and resource *installed* in this workspace.

    The agent's authorization pick-list is drawn from this catalog.
    ``/api/agent_tools`` remains the global taxonomy reference.
    """
    return {
        "items": (
            _resolve_mcp_tools(workspace_id, store, mcp_registry)
            + _resolve_host_env_tools(workspace_id, store)
            + _resolve_resource_bindings(workspace_id, store)
        ),
    }
