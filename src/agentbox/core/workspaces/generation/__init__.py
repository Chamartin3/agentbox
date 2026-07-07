"""Workspace environment generation.

``WorkspaceConstructor`` is the entry point: hand it the active engine
recipes and it generates config files and materializes resource bindings
onto a workdir, agnostic to which engines are involved.
"""

from agentbox.core.data.workenv import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkenvConfig,
)
from agentbox.core.workspaces.generation.construct import (
    ExtraItemsFn,
    WorkspaceConstructor,
)
from agentbox.core.workspaces.generation.materialize import MaterializeOutcome
from agentbox.core.data.workenv import (
    Item,
    RenderedDir,
    Role,
)
from agentbox.core.data.workenv import Recipe

__all__ = [
    "WorkspaceConstructor",
    "ExtraItemsFn",
    "AgentRef",
    "Item",
    "MaterializeOutcome",
    "McpRef",
    "Permissions",
    "Recipe",
    "RenderedDir",
    "ResourceRef",
    "Role",
    "WorkenvConfig",
]
