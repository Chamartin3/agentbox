"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
startup via `_metadata.create_all(engine)`; no migration tool is used.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
    text,
)

from agentbox.core.constants import ResourceType
from agentbox.core.data._metadata import metadata

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

"""Resource repository: resources, versions, blobs, bindings, shared resources."""

shared_resources = Table(
    "shared_resources",
    metadata,
    Column("id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("content", String, nullable=True),
    Column("config_json", String, nullable=True),
    Column("sha256", String, nullable=False),
    Column("is_active", Integer, nullable=False, server_default="0"),
    Column("author", String, nullable=True),
    Column("changelog", String, nullable=True),
    Column("tags", String, nullable=True),
    Column("created_at", String, nullable=False),
    # Composite primary key: stable id + monotonic version per resource
    Index("pk_shared_resources", "id", "version", unique=True),
    # Index for catalog browsing by kind and active status
    Index("ix_shared_resources_kind_active", "kind", "is_active"),
    # Index for fast active lookup by resource id
    Index("ix_shared_resources_id_active", "id", "is_active"),
)

resources = Table(
    "resources",
    metadata,
    Column("id", String, primary_key=True),
    Column("slug", String, nullable=False),
    Column("type", String, nullable=False),
    Column("display_name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("tags", String, nullable=True),
    Column("active_version_id", String, nullable=True),
    Column("status", String, nullable=False, server_default="active"),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    CheckConstraint(
        f"type IN ({_RESOURCE_TYPES_SQL})",
        name="resources_type_check",
    ),
    UniqueConstraint("slug", name="uq_resources_slug"),
    Index("ix_resources_type", "type"),
    Index("ix_resources_status", "status"),
)

resource_versions = Table(
    "resource_versions",
    metadata,
    Column("id", String, primary_key=True),
    Column("resource_id", String, ForeignKey("resources.id"), nullable=False),
    Column("version_number", Integer, nullable=False),
    Column("is_draft", Integer, nullable=False, server_default="0"),
    Column("import_source", String, nullable=False),
    Column("source_metadata", String, nullable=True),
    Column("content_hash", String, nullable=False),
    Column("byte_size", Integer, nullable=False, server_default="0"),
    Column("metadata_json", String, nullable=True),
    Column("changelog", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    CheckConstraint(
        "import_source IN ('upload', 'host_path', 'toml_migration', 'db_only')",
        name="resource_versions_import_source_check",
    ),
    CheckConstraint("is_draft IN (0, 1)", name="resource_versions_is_draft_bool"),
    UniqueConstraint(
        "resource_id", "version_number", name="uq_resource_versions_number"
    ),
    Index("ix_resource_versions_resource", "resource_id"),
)

resource_blobs = Table(
    "resource_blobs",
    metadata,
    Column("id", String, primary_key=True),
    Column(
        "resource_version_id",
        String,
        ForeignKey("resource_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("relative_path", String, nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("content_text", String, nullable=True),
    Column("mime_type", String, nullable=True),
    Column("size_bytes", Integer, nullable=False, server_default="0"),
    UniqueConstraint(
        "resource_version_id", "relative_path", name="uq_resource_blobs_path"
    ),
    Index("ix_resource_blobs_version", "resource_version_id"),
)

active_resource_versions = Table(
    "active_resource_versions",
    metadata,
    Column("resource_id", String, ForeignKey("resources.id"), primary_key=True),
    Column(
        "version_id",
        String,
        ForeignKey("resource_versions.id"),
        nullable=False,
    ),
    Column("activated_at", String, nullable=False),
    Column("activated_by", String, nullable=True),
)

# --- Plan 02: agent prompt-embed bindings ---

agent_prompt_resource_bindings = Table(
    "agent_prompt_resource_bindings",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("resource_id", String, ForeignKey("resources.id"), nullable=False),
    Column("marker", String, nullable=True),
    Column("mode", String, nullable=True),
    Column("slot", String, nullable=True),
    Column(
        "attach_as_reference",
        Integer,
        nullable=False,
        server_default="0",
    ),
    Column(
        "pinned_version_id", String, ForeignKey("resource_versions.id"), nullable=True
    ),
    Column("display_order", Integer, nullable=False, server_default="0"),
    Column("required", Integer, nullable=False, server_default="1"),
    Column("changelog", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    CheckConstraint(
        "mode IS NULL OR mode IN ('inline', 'skill_primer', 'name_only', 'manifest')",
        name="agent_prompt_bindings_mode_check",
    ),
    CheckConstraint(
        "slot IS NULL OR slot IN ("
        "'system', 'user_template', 'input_schema', 'output_schema'"
        ")",
        name="agent_prompt_bindings_slot_check",
    ),
    CheckConstraint(
        "(slot IS NOT NULL) OR (marker IS NOT NULL AND mode IS NOT NULL)",
        name="agent_prompt_bindings_slot_or_marker",
    ),
    CheckConstraint("required IN (0, 1)", name="agent_prompt_bindings_required_bool"),
    CheckConstraint(
        "attach_as_reference IN (0, 1)",
        name="agent_prompt_bindings_reference_bool",
    ),
    UniqueConstraint(
        "agent_id",
        "marker",
        "resource_id",
        name="uq_agent_prompt_bindings_triple",
    ),
    Index("ix_agent_prompt_bindings_agent", "agent_id"),
    Index(
        "uq_agent_prompt_bindings_slot",
        "agent_id",
        "slot",
        unique=True,
        sqlite_where=text("slot IS NOT NULL"),
    ),
)

# Plan 23: validation contracts / bindings retired. Validators now live
# inline on agent_versions.config_json["{input,output}"].validators —
# see core/agent/config.resolve_output_config and
# api/routes/agent_validation.

# --- Plan 03: workspace file-materialize bindings ---

workspace_file_resource_bindings = Table(
    "workspace_file_resource_bindings",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("resource_id", String, ForeignKey("resources.id"), nullable=False),
    Column("target_path", String, nullable=True),
    Column(
        "pinned_version_id", String, ForeignKey("resource_versions.id"), nullable=True
    ),
    Column("materialize_mode", String, nullable=False, server_default="copy"),
    Column("on_conflict", String, nullable=False, server_default="error"),
    Column("display_order", Integer, nullable=False, server_default="0"),
    Column("changelog", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    CheckConstraint(
        "materialize_mode IN ('copy', 'symlink', 'mount')",
        name="workspace_file_bindings_mode_check",
    ),
    CheckConstraint(
        "on_conflict IN ('error', 'overwrite', 'skip')",
        name="workspace_file_bindings_on_conflict_check",
    ),
    UniqueConstraint(
        "workspace_id",
        "resource_id",
        "target_path",
        name="uq_workspace_file_bindings_triple",
    ),
    Index("ix_workspace_file_bindings_workspace", "workspace_id"),
)
