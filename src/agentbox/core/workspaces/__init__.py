"""Public facade for the Workspace domain.

Re-exports the names execution/ callers need so they never import from
``core.workspace.*`` or ``core.resource.*`` submodules directly.
"""

from agentbox.core.resources.skills import discover_skills as discover_skills
from agentbox.core.workspaces.subagent_render import (
    materialize_subagents as materialize_subagents,
)
from agentbox.core.resources.workspace_materialize import (
    materialize_workspace as materialize_workspace,
)
from agentbox.core.workspaces.envdoc.renderers.agents_md import (
    AgentsMdRenderer as AgentsMdRenderer,
)
from agentbox.core.workspaces.envdoc.renderers.base import (
    RuntimeContext as RuntimeContext,
)
from agentbox.core.workspaces.envdoc.renderers.claude_md import (
    ClaudeMdRenderer as ClaudeMdRenderer,
)
from agentbox.core.workspaces.envdoc.schema import (
    EnvDocContent as EnvDocContent,
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
    write_secrets as write_secrets,
)

__all__ = [
    "AgentsMdRenderer",
    "ClaudeMdRenderer",
    "EnvDocContent",
    "McpRegistry",
    "RuntimeContext",
    "WorkspaceInfo",
    "discover_skills",
    "load_capabilities",
    "materialize_subagents",
    "materialize_workspace",
    "resolve_path",
    "write_secrets",
]
