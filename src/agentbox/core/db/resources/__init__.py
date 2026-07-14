"""Resources domain — resource catalog and bindings.

One file per table (entity + manager together). The manager is the public
surface; the entity is importable directly for cross-domain FK references.
"""
from __future__ import annotations

from agentbox.core.db.resources.binding import (
    AgentPromptResourceBinding,
    AgentPromptResourceBindingManager,
    WorkspaceFileResourceBinding,
    WorkspaceFileResourceBindingManager,
)
from agentbox.core.db.resources.resource import (
    ActiveResourceVersion,
    ActiveResourceVersionManager,
    Resource,
    ResourceBlob,
    ResourceBlobManager,
    ResourceVersion,
    ResourceVersionManager,
    ResourceManager,
)
from agentbox.core.db.resources.shared_resource import (
    SharedResource,
    SharedResourceManager,
)

__all__ = [
    # binding entities + managers
    "AgentPromptResourceBinding",
    "AgentPromptResourceBindingManager",
    "WorkspaceFileResourceBinding",
    "WorkspaceFileResourceBindingManager",
    # resource entities + managers
    "ActiveResourceVersion",
    "ActiveResourceVersionManager",
    "Resource",
    "ResourceBlob",
    "ResourceBlobManager",
    "ResourceVersion",
    "ResourceVersionManager",
    "ResourceManager",
    # shared_resource entity + manager
    "SharedResource",
    "SharedResourceManager",
]
