"""Public facade for the Workspace domain.

Re-exports the names execution/ callers need so they never import from
``core.workspace.*`` or ``core.resource.*`` submodules directly.
"""

from agentbox.core.resource.skills import discover_skills as discover_skills
from agentbox.core.resource.subagent_render import (
    materialize_subagents as materialize_subagents,
)
from agentbox.core.resource.workspace_materialize import (
    materialize_workspace as materialize_workspace,
)
from agentbox.core.workspace.env_doc.renderers.agents_md import (
    AgentsMdRenderer as AgentsMdRenderer,
)
from agentbox.core.workspace.env_doc.renderers.base import (
    RuntimeContext as RuntimeContext,
)
from agentbox.core.workspace.env_doc.renderers.claude_md import (
    ClaudeMdRenderer as ClaudeMdRenderer,
)
from agentbox.core.workspace.env_doc.schema import (
    EnvDocContent as EnvDocContent,
)
from agentbox.core.workspace.manager import (
    load_capabilities as load_capabilities,
    resolve_path as resolve_path,
)

__all__ = [
    "AgentsMdRenderer",
    "ClaudeMdRenderer",
    "EnvDocContent",
    "RuntimeContext",
    "discover_skills",
    "load_capabilities",
    "materialize_subagents",
    "materialize_workspace",
    "resolve_path",
]
