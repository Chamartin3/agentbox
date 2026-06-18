"""SharedResourceManager — cross-repo resource sharing CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.resources.shared_resource import SharedResource


class SharedResourceManager(Manager[SharedResource]):
    """Manager for the ``shared_resources`` table (composite PK id+version)."""
    model = SharedResource
