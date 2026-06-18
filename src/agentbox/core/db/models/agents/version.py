"""Agent version and version-file models.

Maps to the ``agent_versions``, ``agent_version_files``,
``agent_version_ratings``, and ``agent_version_comments`` tables.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


class AgentVersion(Entity, table=True):
    """A versioned snapshot of an agent's definition and prompt content."""

    __tablename__ = tablename("agent_versions")

    id: int = Field(default=None, primary_key=True)
    agent_id: str = Field(nullable=False)
    version: int = Field(nullable=False)
    source_path: str = Field(nullable=False)
    source_format: str = Field(nullable=False)
    content_snapshot: str = Field(nullable=False)
    prompt_snapshot: str = Field(nullable=False)
    content_hash: str = Field(nullable=False)
    author: str = Field(nullable=False)
    changelog: str = Field(nullable=False, default="")
    is_legacy: int = Field(nullable=False, default=0)
    created_at: str = Field(nullable=False)
    config_json: Optional[str] = Field(default=None)
    prompt_content: Optional[str] = Field(default=None)
    source: str = Field(nullable=False, default="manifest")
    resolved_tool_grants: Optional[list[str]] = Field(default=None, sa_type=JSON)

    __table_args__ = tableargs(  
        Index("idx_agent_versions_agent", "agent_id", "version", unique=True),
    )


class AgentVersionFile(Entity, table=True):
    """A file attached to a particular agent version."""

    __tablename__ = tablename("agent_version_files")

    id: int = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="agent_versions.id", ondelete="CASCADE", nullable=False)
    relative_path: str = Field(nullable=False)
    kind: str = Field(nullable=False)
    content: str = Field(nullable=False)
    sha256: str = Field(nullable=False)
    source_uri: Optional[str] = Field(default=None)
    position: int = Field(nullable=False, default=0)
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(  
        UniqueConstraint("version_id", "relative_path", name="uq_version_file_path"),
        Index("idx_agent_version_files_version", "version_id"),
    )


class AgentVersionRating(Entity, table=True):
    """A user rating (1-5) for an agent version."""

    __tablename__ = tablename("agent_version_ratings")

    version_id: int = Field(foreign_key="agent_versions.id", primary_key=True)
    rating: int = Field(nullable=False)
    rater: str = Field(nullable=False)
    rated_at: str = Field(nullable=False)


class AgentVersionComment(Entity, table=True):
    """A user comment on an agent version."""

    __tablename__ = tablename("agent_version_comments")

    id: int = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="agent_versions.id", nullable=False)
    author: str = Field(nullable=False)
    body: str = Field(nullable=False)
    created_at: str = Field(nullable=False)
