"""Central resource repository (Plan 01).

DB-backed, versioned repository of resources (documents, folders, skills)
that replaces per-agent TOML declarations. Bytes live in the DB
(``resource_blobs``); the host filesystem is no longer required.
"""

from agentbox.core.data.resources.models import (
    Resource,
    ResourceBlob,
    ResourceVersion,
)

__all__ = ["Resource", "ResourceBlob", "ResourceVersion"]
