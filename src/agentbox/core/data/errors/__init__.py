"""Domain exception hierarchy.

Re-exports every exception class. Consumers import from
``agentbox.core.data.errors`` (or the ``agentbox.core.data`` facade).
"""

from agentbox.core.data.errors.agents import (
    AgentAlreadyExists,
    AgentNotFound,
    AgentServiceError,
    DuplicateVersionFile,
    VersionFileNotFound,
    VersionNotDraft,
    VersionNotFound,
)
from agentbox.core.data.errors.base import AgentboxError
from agentbox.core.data.errors.execution import (
    AgentDisabled,
    InvalidRunInput,
    RunNotFound,
)
from agentbox.core.data.errors.schemas import InconsistentSchema, UnsupportedSchema
from agentbox.core.data.errors.workspaces import (
    LaunchTargetUnresolved,
    WorkspaceError,
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
)

__all__ = [
    "AgentAlreadyExists",
    "AgentDisabled",
    "AgentNotFound",
    "AgentServiceError",
    "AgentboxError",
    "DuplicateVersionFile",
    "InconsistentSchema",
    "InvalidRunInput",
    "LaunchTargetUnresolved",
    "RunNotFound",
    "UnsupportedSchema",
    "VersionFileNotFound",
    "VersionNotDraft",
    "VersionNotFound",
    "WorkspaceError",
    "WorkspaceExists",
    "WorkspaceNotFound",
    "WorkspacePathEscape",
]
