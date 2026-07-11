"""Domain exception hierarchy.

Re-exports every exception class. Consumers import from
``agentbox.core.data.errors`` (or the ``agentbox.core.data`` facade).
"""

from agentbox.core.data.errors.base import AgentboxError
from agentbox.core.data.errors.schemas import InconsistentSchema, UnsupportedSchema
from agentbox.core.data.errors.workspaces import (
    WorkspaceError,
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)

__all__ = [
    "AgentboxError",
    "InconsistentSchema",
    "UnsupportedSchema",
    "WorkspaceError",
    "WorkspaceExists",
    "WorkspaceNotFound",
    "WorkspacePathEscape",
]
