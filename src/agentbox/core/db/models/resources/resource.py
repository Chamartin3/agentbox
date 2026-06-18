"""Resource, version, blob, and active-version models.

Maps to the ``resources``, ``resource_versions``, ``resource_blobs``,
and ``active_resource_versions`` tables.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index, UniqueConstraint, LargeBinary

from agentbox.core.db.base.model import Entity


class Resource(Entity, table=True):
    """A versioned resource (document, folder, skill, schema, or script)."""

    __tablename__ = tablename("resources")

    id: str = Field(primary_key=True)
    slug: str = Field(nullable=False)
    type: str = Field(nullable=False)
    display_name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    tags: Optional[str] = Field(default=None)
    active_version_id: Optional[str] = Field(default=None)
    status: str = Field(nullable=False, default="active")
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("slug", name="uq_resources_slug"),
        Index("ix_resources_type", "type"),
        Index("ix_resources_status", "status"),
    )


class ResourceVersion(Entity, table=True):
    """A specific version of a resource."""

    __tablename__ = tablename("resource_versions")

    id: str = Field(primary_key=True)
    resource_id: str = Field(foreign_key="resources.id", nullable=False)
    version_number: int = Field(nullable=False)
    is_draft: int = Field(nullable=False, default=0)
    import_source: str = Field(nullable=False)
    source_metadata: Optional[str] = Field(default=None)
    content_hash: str = Field(nullable=False)
    byte_size: int = Field(nullable=False, default=0)
    metadata_json: Optional[str] = Field(default=None)
    changelog: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
    created_by: Optional[str] = Field(default=None)

    __table_args__ = tableargs(  
        UniqueConstraint("resource_id", "version_number", name="uq_resource_versions_number"),
        Index("ix_resource_versions_resource", "resource_id"),
    )


class ResourceBlob(Entity, table=True):
    """A file/blob attached to a resource version."""

    __tablename__ = tablename("resource_blobs")

    id: str = Field(primary_key=True)
    resource_version_id: str = Field(
        foreign_key="resource_versions.id", ondelete="CASCADE", nullable=False,
    )
    relative_path: str = Field(nullable=False)
    content: bytes = Field(nullable=False, sa_type=LargeBinary)
    content_text: Optional[str] = Field(default=None)
    mime_type: Optional[str] = Field(default=None)
    size_bytes: int = Field(nullable=False, default=0)

    __table_args__ = tableargs(  
        UniqueConstraint("resource_version_id", "relative_path", name="uq_resource_blobs_path"),
        Index("ix_resource_blobs_version", "resource_version_id"),
    )


class ActiveResourceVersion(Entity, table=True):
    """Points to the currently active version for each resource."""

    __tablename__ = tablename("active_resource_versions")

    resource_id: str = Field(foreign_key="resources.id", primary_key=True)
    version_id: str = Field(foreign_key="resource_versions.id", nullable=False)
    activated_at: str = Field(nullable=False)
    activated_by: Optional[str] = Field(default=None)
