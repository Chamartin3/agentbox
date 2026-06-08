"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
Alembic is the primary migration tool; metadata.create_all(engine) is the fallback.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)

from agentbox.core.constants import ResourceType
from agentbox.core.data._metadata import metadata

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

"""Agent identity, versioning, prompts, sync, config events, tool grants."""

agent_versions = Table(
    "agent_versions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("source_path", String, nullable=False),
    Column("source_format", String, nullable=False),
    Column("content_snapshot", String, nullable=False),
    Column("prompt_snapshot", String, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("author", String, nullable=False),
    Column("changelog", String, nullable=False, server_default=""),
    Column("is_legacy", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    # DB-as-source-of-truth columns:
    Column("config_json", String, nullable=True),
    Column("prompt_content", String, nullable=True),
    Column("source", String, nullable=False, server_default="manifest"),
    Column("resolved_tool_grants", JSON, nullable=True),  # list[str], frozen at publish
    Index("idx_agent_versions_agent", "agent_id", "version", unique=True),
)

active_agent_versions = Table(
    "active_agent_versions",
    metadata,
    Column("agent_id", String, primary_key=True),
    Column(
        "version_id",
        Integer,
        ForeignKey("agent_versions.id"),
        nullable=False,
    ),
    Column("activated_at", String, nullable=False),
)

agent_meta = Table(
    "agent_meta",
    metadata,
    Column("agent_id", String, primary_key=True),
    Column("sync_mode", String, nullable=False, server_default="off"),
    Column("export_to_disk", Integer, nullable=False, server_default="0"),
    Column("source_path", String, nullable=True),
    Column("source_format", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("deleted_at", String, nullable=True),
    Column("disabled_at", String, nullable=True),
)

agent_version_comments = Table(
    "agent_version_comments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("version_id", Integer, ForeignKey("agent_versions.id"), nullable=False),
    Column("author", String, nullable=False),
    Column("body", String, nullable=False),
    Column("created_at", String, nullable=False),
)

prompt_versions = Table(
    "prompt_versions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("content", String, nullable=False),
    Column("author", String, nullable=False, server_default="system"),
    Column("changelog", String, nullable=False, server_default=""),
    Column("is_draft", Integer, nullable=False, server_default="0"),
    Column("content_hash", String, nullable=True),
    Column("created_at", String, nullable=False),
    Index("idx_prompt_versions_agent", "agent_id", "version", unique=True),
)

agent_version_files = Table(
    "agent_version_files",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "version_id",
        Integer,
        ForeignKey("agent_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("relative_path", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("content", String, nullable=False),
    Column("sha256", String, nullable=False),
    Column("source_uri", String, nullable=True),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    UniqueConstraint("version_id", "relative_path", name="uq_version_file_path"),
    Index("idx_agent_version_files_version", "version_id"),
)

agent_version_ratings = Table(
    "agent_version_ratings",
    metadata,
    Column("version_id", Integer, ForeignKey("agent_versions.id"), primary_key=True),
    Column("rating", Integer, nullable=False),
    Column("rater", String, nullable=False),
    Column("rated_at", String, nullable=False),
    CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
)

agent_sync = Table(
    "agent_sync",
    metadata,
    Column("agent_id", String, primary_key=True),
    Column("proxy_path", String),
    Column("sync_mode", String, nullable=False, server_default="manual"),
    Column("sync_policy", String, nullable=False, server_default="db_wins"),
    Column("last_file_hash", String),
    Column("last_file_mtime", String),
    Column("last_sync_at", String),
)

agent_runner_profiles = Table(
    "agent_runner_profiles",
    metadata,
    Column("agent_id", String, primary_key=True),
    Column(
        "runner_profile_id", String, ForeignKey("runner_profiles.id"), nullable=False
    ),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

# --- Plan 01: central resource repository ---

agents = Table(
    "agents",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("created_at", String, nullable=False),
)

agent_tool_grants = Table(
    "agent_tool_grants",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "agent_id",
        String,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("tool_name", String, nullable=False),
    Column("changelog", String, nullable=False),  # min 3 chars, enforced in mixin
    Column("granted_at", String, nullable=False),
    Column("granted_by", String, nullable=True),
    Column(
        "revoked_at", String, nullable=True
    ),  # NULL = active; set to iso timestamp on revoke
    Column("revoked_by", String, nullable=True),
    Column("revoke_changelog", String, nullable=True),
    Index("ix_agent_tool_grants_agent", "agent_id"),
    UniqueConstraint("agent_id", "tool_name", name="uq_agent_tool_grant"),
)

agent_config_events = Table(
    "agent_config_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("field", String, nullable=False),
    Column("from_value", String, nullable=True),
    Column("to_value", String, nullable=True),
    Column("author", String, nullable=False),
    Column("source", String, nullable=False),
    Column("created_at", String, nullable=False),
    Index("ix_agent_config_events_agent", "agent_id"),
    Index("ix_agent_config_events_created", "created_at"),
)
