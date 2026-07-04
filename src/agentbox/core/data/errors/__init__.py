"""Domain exception hierarchy.

Re-exports every exception class. Consumers import from
``agentbox.core.data.errors`` (or the ``agentbox.core.data`` facade).
"""

from agentbox.core.data.errors.base import AgentboxError
from agentbox.core.data.errors.workspaces import (
    WorkspaceError,
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)

__all__ = [
    "AgentboxError",
    "WorkspaceError",
    "WorkspaceExists",
    "WorkspaceNotFound",
    "WorkspacePathEscape",
]
