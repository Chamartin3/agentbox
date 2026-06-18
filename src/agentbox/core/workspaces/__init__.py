"""Public facade for the Workspace domain.

Re-exports the names execution/ callers need so they never import from
``core.workspace.*`` or ``core.resource.*`` submodules directly.
"""

from agentbox.core.resources.skills import discover_skills as discover_skills
from agentbox.core.resources.binding_materialize import (
    materialize_workspace as materialize_workspace,
)
from agentbox.core.workspaces.crud import (
    WorkspaceInfo as WorkspaceInfo,
)
from agentbox.core.workspaces.manager import (
    load_capabilities as load_capabilities,
    resolve_path as resolve_path,
)
from agentbox.core.workspaces.mcp.client.registry import (
    McpRegistry as McpRegistry,
)
from agentbox.core.workspaces.prep import (
    load_workspace_permissions as load_workspace_permissions,
    prepare_run_workdir as prepare_run_workdir,
    prompt_resolution_to_snapshot as prompt_resolution_to_snapshot,
    render_env_doc as render_env_doc,
    resolve_agent_prompt_bindings as resolve_agent_prompt_bindings,
    resolve_workspace_resources as resolve_workspace_resources,
    resolve_workspace_subagents as resolve_workspace_subagents,
    workspace_outcomes_to_snapshot as workspace_outcomes_to_snapshot,
    write_secrets as write_secrets,
)

__all__ = [
    "McpRegistry",
    "WorkspaceInfo",
    "discover_skills",
    "load_capabilities",
    "load_workspace_permissions",
    "materialize_workspace",
    "prepare_run_workdir",
    "prompt_resolution_to_snapshot",
    "render_env_doc",
    "resolve_agent_prompt_bindings",
    "resolve_path",
    "resolve_workspace_resources",
    "resolve_workspace_subagents",
    "workspace_outcomes_to_snapshot",
    "write_secrets",
]
