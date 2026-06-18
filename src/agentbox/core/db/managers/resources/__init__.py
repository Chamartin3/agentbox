"""Resources domain managers — catalog index."""
from __future__ import annotations

from agentbox.core.db.managers.resources.resource import (
    ActiveResourceVersionManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
)
from agentbox.core.db.managers.resources.shared_resource import SharedResourceManager
from agentbox.core.db.managers.resources.binding import AgentPromptResourceBindingManager, WorkspaceFileResourceBindingManager

__all__ = [
    "ActiveResourceVersionManager",
    "AgentPromptResourceBindingManager",
    "ResourceBlobManager",
    "ResourceManager",
    "ResourceVersionManager",
    "SharedResourceManager",
    "WorkspaceFileResourceBindingManager",
]
