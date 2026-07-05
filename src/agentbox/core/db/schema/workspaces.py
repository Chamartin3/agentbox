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

from agentbox.core.data.constants import ResourceType
from agentbox.core.db._metadata import metadata

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

"""Workspace registry + satellite tables (subagents, env_doc, mcp, permissions)."""

workspace_subagents = Table(
    "workspace_subagents",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("agent_id", String, nullable=False),
    Column("alias", String, nullable=False),
    Column("display_order", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    UniqueConstraint("workspace_id", "alias", name="uq_workspace_subagents_alias"),
    Index("ix_workspace_subagents_workspace", "workspace_id"),
)

workspace_env_doc_versions = Table(
    "workspace_env_doc_versions",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("version_number", Integer, nullable=False),
    Column("content_json", JSON, nullable=False),
    Column("is_draft", Integer, nullable=False, server_default="0"),
    Column("changelog", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    UniqueConstraint(
        "workspace_id", "version_number", name="uq_workspace_env_doc_version"
    ),
    Index("ix_workspace_env_doc_versions_workspace_id", "workspace_id"),
)

workspace_mcp_overrides = Table(
    "workspace_mcp_overrides",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("server_name", String, nullable=False),
    Column("enabled", Integer, nullable=False),
    Column("config_overrides", JSON, nullable=True),
    Column("changelog", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    UniqueConstraint("workspace_id", "server_name", name="uq_workspace_mcp_override"),
    Index("ix_workspace_mcp_overrides_workspace", "workspace_id"),
)

workspace_mcp_tool_overrides = Table(
    "workspace_mcp_tool_overrides",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("server_name", String, nullable=False),
    Column("tool_name", String, nullable=False),
    Column("enabled", Integer, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    UniqueConstraint(
        "workspace_id",
        "server_name",
        "tool_name",
        name="uq_workspace_mcp_tool_override",
    ),
    Index("ix_workspace_mcp_tool_overrides_workspace", "workspace_id"),
)

workspace_mcp_policies = Table(
    "workspace_mcp_policies",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column(
        "default_policy",
        String,
        nullable=False,
        server_default="allow_all_unless_disabled",
    ),
    CheckConstraint(
        "default_policy IN ('allow_all_unless_disabled', 'deny_all_unless_enabled')",
        name="workspace_mcp_policy_check",
    ),
)

workspace_host_env_grants = Table(
    "workspace_host_env_grants",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column(
        "profile_id",
        String,
        ForeignKey("host_env_profiles.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("overrides", JSON, nullable=True),
    Column("changelog", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
)

workspace_runtime_permissions = Table(
    "workspace_runtime_permissions",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column("allowed_builtin_tools", JSON, nullable=True),
    Column("files", JSON, nullable=True),
    Column("max_tokens", Integer, nullable=True),
    Column("allow_file_write", Integer, nullable=True),
    Column("allow_network", Integer, nullable=True),
    Column("updated_at", String, nullable=False),
    Column("updated_by", String, nullable=True),
)

workspace_env_docs = Table(
    "workspace_env_docs",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column(
        "active_version_id",
        String,
        ForeignKey("workspace_env_doc_versions.id", ondelete="SET NULL"),
        nullable=True,
    ),
)

# Canonical workspace registry. Source of truth for "what workspaces exist".
# Satellite tables (workspace_*) reference by name but are not enforced as FKs
# for backwards-compat with pre-registry rows; the WorkspacesMixin handles
# cascade delete explicitly.

workspaces = Table(
    "workspaces",
    metadata,
    Column("name", String, primary_key=True),
    Column("description", String, nullable=True),
    Column("path", String, nullable=True),
    # 'manifest' = legacy (imported from agentbox.toml era), 'db' = created via API
    Column("source", String, nullable=False, server_default="db"),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    Column("updated_at", String, nullable=False),
    CheckConstraint(
        "source IN ('manifest', 'db')",
        name="workspaces_source_check",
    ),
)
