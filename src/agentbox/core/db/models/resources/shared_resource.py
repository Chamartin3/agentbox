"""SharedResource model — cross-repository resource sharing.

Maps to the ``shared_resources`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class SharedResource(Entity, table=True):
    """A resource shared across repositories, versioned by an id+version composite key."""

    __tablename__ = tablename("shared_resources")

    id: str = Field(primary_key=True)
    version: int = Field(primary_key=True)
    kind: str = Field(nullable=False)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    config_json: Optional[str] = Field(default=None)
    sha256: str = Field(nullable=False)
    is_active: int = Field(nullable=False, default=0)
    author: Optional[str] = Field(default=None)
    changelog: Optional[str] = Field(default=None)
    tags: Optional[str] = Field(default=None)
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        Index("pk_shared_resources", "id", "version", unique=True),
        Index("ix_shared_resources_kind_active", "kind", "is_active"),
        Index("ix_shared_resources_id_active", "id", "is_active"),
    )
