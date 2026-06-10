"""Load a WorkenvConfig from the authoritative DB state.

Wraps the existing ``core/service/workspaces/configs.py`` DB resolution.
No logic moves yet — only the wrapping.  This unblocks downstream phases
without touching live code paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentbox.core.data import SessionStore
from agentbox.core.workspaces.generation.config import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkenvConfig,
)

if TYPE_CHECKING:
    from agentbox.config import Settings


def load_workenv(
    store: SessionStore,
    workspace_id: str,
    *,
    settings: Settings,
    permissions: dict[str, Any] | None = None,
) -> WorkenvConfig:
    """Resolve a ``WorkenvConfig`` from the DB for *workspace_id*.

    Args:
        store: Active session store (DB connection).
        workspace_id: Identifier of the workspace to load.
        settings: Application settings (used for project-root resolution).
        permissions: Pre-resolved effective permissions dict.  Callers in
            the service layer should resolve this via
            ``load_effective_permissions`` before calling here so that
            ``from_db.py`` stays free of ``core.service`` imports.
            Defaults to an empty permissions set when ``None``.
    """
    ws_row = store.get_workspace(workspace_id)
    workspace_name = workspace_id

    # Main agent (if one exists for the workspace)
    agent_def = store.get_agent_def(workspace_id)
    agents: list[AgentRef] = []
    if agent_def is not None:
        agents.append(AgentRef(id=workspace_id, role="main"))

    # Subagents
    for sa in store.list_workspace_subagents(workspace_id):
        agents.append(AgentRef(id=sa["subagent_id"], role="subagent"))

    # Resource bindings
    resources: list[ResourceRef] = []
    skills: list[ResourceRef] = []
    for b in store.list_workspace_file_bindings(workspace_id):
        resources.append(ResourceRef(id=b["resource_id"]))

    # MCP servers (project-level + workspace overrides)
    project_servers = store.get_project_mcp_servers()
    server_overrides = {
        o["server_name"]: o
        for o in store.list_workspace_mcp_server_overrides(workspace_id)
    }
    tool_overrides = store.list_workspace_mcp_tool_overrides(workspace_id)

    mcp_servers: list[McpRef] = []
    for srv in project_servers:
        srv_override = server_overrides.get(srv.name, {})
        if srv_override.get("enabled") is False:
            continue
        srv_disabled_tools = [
            t["tool_name"]
            for t in tool_overrides
            if t["server_name"] == srv.name and not t["enabled"]
        ]
        mcp_servers.append(
            McpRef(
                name=srv.name,
                config={
                    k: v
                    for k, v in {
                        "url": srv.url,
                        "command": srv.command,
                        "transport": srv.transport,
                    }.items()
                    if v is not None
                },
                disabled_tools=srv_disabled_tools,
            )
        )

    # Permissions — resolved by the caller; default to an empty set.
    resolved_permissions = Permissions(data=dict(permissions) if permissions else {})

    # Env doc
    env_doc = store.get_active_env_doc(workspace_id)
    env_doc_content: str | ResourceRef | None = None
    if env_doc is not None:
        content_json = env_doc.get("content_json")
        if isinstance(content_json, dict):
            body = content_json.get("body") or content_json.get("content") or ""
            env_doc_content = body if isinstance(body, str) else str(body)

    return WorkenvConfig(
        name=workspace_name,
        description=(
            getattr(ws_row, "description", "")
            if ws_row is not None
            else ""
        ).strip() or "",
        env_doc=env_doc_content,
        agents=agents,
        resources=resources,
        skills=skills,
        mcp_servers=mcp_servers,
        permissions=resolved_permissions,
        env={},
    )
