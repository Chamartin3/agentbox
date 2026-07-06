"""Public facade for the Workspace domain.

Re-exports the names execution/ callers need so they never import from
``core.workspace.*`` or ``core.resource.*`` submodules directly.
"""

from agentbox.core.resources.skills import discover_skills as discover_skills
from agentbox.core.workspaces.generation.materialize import (
    materialize_workspace as materialize_workspace,
)
from agentbox.core.workspaces.workdir import (
    WorkspaceInfo as WorkspaceInfo,
    resolve_path as resolve_path,
)
from agentbox.core.mcp.client.registry import (
    McpRegistry as McpRegistry,
)
from agentbox.core.workspaces.prep import (
    load_workspace_permissions as load_workspace_permissions,
    prepare_run_workdir as prepare_run_workdir,
    render_env_doc as render_env_doc,
    resolve_workspace_resources as resolve_workspace_resources,
    resolve_workspace_subagents as resolve_workspace_subagents,
    write_secrets as write_secrets,
)

__all__ = [
    "McpRegistry",
    "WorkspaceInfo",
    "discover_skills",
    "load_workspace_permissions",
    "materialize_workspace",
    "prepare_run_workdir",
    "render_env_doc",
    "resolve_path",
    "resolve_workspace_resources",
    "resolve_workspace_subagents",
    "write_secrets",
]
