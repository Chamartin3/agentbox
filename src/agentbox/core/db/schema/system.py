"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
Alembic is the primary migration tool; metadata.create_all(engine) is the fallback.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    Index,
    String,
    Table,
    UniqueConstraint,
)

from agentbox.core.constants import ResourceType
from agentbox.core.db._metadata import metadata

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

"""System tables: api_tokens, settings, host_env, mcp_discovery."""

host_env_profiles = Table(
    "host_env_profiles",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("grants", JSON, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    UniqueConstraint("name", name="uq_host_env_profile_name"),
)

host_env_call_log = Table(
    "host_env_call_log",
    metadata,
    Column("id", String, primary_key=True),
    Column("run_id", String, nullable=False),
    Column("workspace_id", String, nullable=False),
    Column("capability", String, nullable=False),
    Column("params", JSON, nullable=True),
    Column("status", String, nullable=False),
    Column("error", String, nullable=True),
    Column("surface", String, nullable=False, server_default="host_env"),
    Column("created_at", String, nullable=False),
    Index("ix_host_env_call_log_run", "run_id"),
    Index("ix_host_env_call_log_workspace", "workspace_id"),
)

api_tokens = Table(
    "api_tokens",
    metadata,
    Column("id", String, primary_key=True),
    Column("environment", String, nullable=False),
    Column("name", String, nullable=False),
    Column("secret_encrypted", String, nullable=False),
    Column("last_four", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    UniqueConstraint("environment", "name", name="uq_api_tokens_env_name"),
)

mcp_tool_discovery_cache = Table(
    "mcp_tool_discovery_cache",
    metadata,
    Column("id", String, primary_key=True),
    Column("server_name", String, nullable=False),
    Column("config_hash", String, nullable=False),
    Column("tools_json", String, nullable=False),
    Column("discovered_at", String, nullable=False),
    UniqueConstraint("server_name", "config_hash", name="uq_mcp_discovery_server_hash"),
    Index("ix_mcp_discovery_server", "server_name"),
)

settings = Table(
    "settings",
    metadata,
    Column("section", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("value_json", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("updated_by", String, nullable=True),
)
