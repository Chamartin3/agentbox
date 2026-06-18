"""Resource, ResourceVersion, ResourceBlob, and ActiveResourceVersion managers."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.resources.resource import (
    ActiveResourceVersion,
    Resource,
    ResourceBlob,
    ResourceVersion,
)


class ResourceManager(Manager[Resource]):
    """Manager for the ``resources`` table."""
    model = Resource


class ResourceVersionManager(Manager[ResourceVersion]):
    """Manager for the ``resource_versions`` table."""
    model = ResourceVersion


class ResourceBlobManager(Manager[ResourceBlob]):
    """Manager for the ``resource_blobs`` table."""
    model = ResourceBlob


class ActiveResourceVersionManager(Manager[ActiveResourceVersion]):
    """Manager for the ``active_resource_versions`` table."""
    model = ActiveResourceVersion
