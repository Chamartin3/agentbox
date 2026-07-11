"""Domain exception hierarchy.

Re-exports every exception class. Consumers import from
``agentbox.core.data.errors`` (or the ``agentbox.core.data`` facade).
"""

from agentbox.core.data.errors.base import AgentboxError
from agentbox.core.data.errors.execution import (
    AgentDisabled,
    InvalidRunInput,
    RunNotFound,
)
from agentbox.core.data.errors.schemas import InconsistentSchema, UnsupportedSchema
from agentbox.core.data.errors.workspaces import (
    WorkspaceError,
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)

__all__ = [
    "AgentDisabled",
    "AgentboxError",
    "InconsistentSchema",
    "InvalidRunInput",
    "RunNotFound",
    "UnsupportedSchema",
    "WorkspaceError",
    "WorkspaceExists",
    "WorkspaceNotFound",
    "WorkspacePathEscape",
]
