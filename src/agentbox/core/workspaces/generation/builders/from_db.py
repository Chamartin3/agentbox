"""Load a WorkenvConfig from the authoritative DB state."""

from __future__ import annotations

from typing import Any

from agentbox.core.config import Settings
from agentbox.core.db import (
    AgentDefManager,
    AgentVersionManager,
    WorkspaceEnvDocVersionManager,
    WorkspaceFileResourceBindingManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpToolOverrideManager,
    WorkspaceManager,
    WorkspaceSubagentManager,
)
from agentbox.core.db.system.config import load_project_mcp_servers
from agentbox.core.workspaces.generation.config import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkenvConfig,
)


def load_workenv(
    workspaces: WorkspaceManager,
    agent_defs: AgentDefManager,
    workspace_subagents: WorkspaceSubagentManager,
    agent_versions: AgentVersionManager,
    workspace_file_resource_bindings: WorkspaceFileResourceBindingManager,
    workspace_mcp_overrides: WorkspaceMcpOverrideManager,
    workspace_mcp_tool_overrides: WorkspaceMcpToolOverrideManager,
    workspace_env_doc_versions: WorkspaceEnvDocVersionManager,
    workspace_id: str,
    *,
    settings: Settings,
    permissions: dict[str, Any] | None = None,
) -> WorkenvConfig:
    """Resolve a ``WorkenvConfig`` from the DB for *workspace_id*."""
    ws_row = workspaces.get_by_name(workspace_id)
    workspace_name = workspace_id

    # Main agent (if one exists for the workspace)
    agent_def = agent_defs.get(workspace_id)
    agents: list[AgentRef] = []
    if agent_def is not None:
        agents.append(AgentRef(id=workspace_id, role="main"))

    # Subagents
    for sa in workspace_subagents.list_for_workspace(workspace_id):
        sub_agent_id = sa["agent_id"]
        active = agent_versions.get_active(sub_agent_id)
        prompt = (
            (active or {}).get("prompt_content")
            or (active or {}).get("prompt_snapshot")
            or ""
        )
        if not prompt:
            continue
        sub_def = agent_defs.get(sub_agent_id)
        agents.append(
            AgentRef(
                id=sa["alias"],
                role="subagent",
                description=getattr(sub_def, "description", "") or "",
                prompt=prompt,
            )
        )

    # Resource bindings
    resources: list[ResourceRef] = []
    skills: list[ResourceRef] = []
    for b in workspace_file_resource_bindings.list_for_workspace(workspace_id):
        resources.append(ResourceRef(id=b["resource_id"]))

    # MCP servers (project-level + workspace overrides)
    project_servers = load_project_mcp_servers()
    server_overrides = {
        o["server_name"]: o
        for o in workspace_mcp_overrides.list_for_workspace(workspace_id)
    }
    tool_overrides = workspace_mcp_tool_overrides.list_for_workspace(workspace_id)

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
    env_doc = workspace_env_doc_versions.get_active(workspace_id)
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
