"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
Alembic is the primary migration tool; metadata.create_all(engine) is the fallback.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
)

from agentbox.core.constants import ResourceType
from agentbox.core.db._metadata import metadata

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

"""Runner profile tables."""

runner_profiles = Table(
    "runner_profiles",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("description", String),
    Column("backend", String, nullable=False),
    Column("provider", String),
    Column("model", String),
    Column("base_url", String),
    Column("api_key_env", String),
    Column("output_mode", String, nullable=False, server_default="auto"),
    Column("params_json", String, nullable=False, server_default="{}"),
    Column("headers_json", String, nullable=False, server_default="{}"),
    Column("extra_args_json", String, nullable=False, server_default="[]"),
    Column("is_enabled", Integer, nullable=False, server_default="1"),
    Column("is_system_default", Integer, nullable=False, server_default="0"),
    Column("api_token_id", String, ForeignKey("api_tokens.id"), nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    CheckConstraint("is_enabled IN (0, 1)", name="runner_profiles_is_enabled_bool"),
    CheckConstraint(
        "is_system_default IN (0, 1)", name="runner_profiles_is_system_default_bool"
    ),
    Index("idx_runner_profiles_backend_provider", "backend", "provider"),
    Index("idx_runner_profiles_enabled", "is_enabled"),
)
