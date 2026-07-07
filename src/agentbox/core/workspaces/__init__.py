"""Public facade for the Workspace domain.

Re-exports the names execution/ callers need so they never import from
``core.workspace.*`` or ``core.resource.*`` submodules directly.
"""

from agentbox.core.resources.skills import discover_skills as discover_skills
from agentbox.core.workspaces.facade import (
    BuildResult as BuildResult,
    WorkspaceInspection as WorkspaceInspection,
    Workspaces as Workspaces,
)
from agentbox.core.workspaces.generation.materialize import (
    materialize_workspace as materialize_workspace,
)
from agentbox.core.workspaces.workdir import (
    WorkspaceInfo as WorkspaceInfo,
    resolve_path as resolve_path,
)
from agentbox.core.workspaces.mcp.client.registry import (
    McpRegistry as McpRegistry,
)

__all__ = [
    "BuildResult",
    "McpRegistry",
    "WorkspaceInfo",
    "WorkspaceInspection",
    "Workspaces",
    "discover_skills",
    "materialize_workspace",
    "resolve_path",
]
