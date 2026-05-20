"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
startup via `_metadata.create_all(engine)`; no migration tool is used.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)

from agentbox.core.constants import ResourceType

metadata = MetaData()

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("workdir", String),
    Column("created_at", String, nullable=False),
    Column("last_used_at", String),
)

runs = Table(
    "runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("session_id", String, ForeignKey("sessions.id")),
    Column("status", String, nullable=False),
    Column("input", String, nullable=False),
    Column("output", String),
    Column("error", String),
    Column("workdir", String),
    Column("transcript_path", String),
    Column("created_at", String, nullable=False),
    Column("finished_at", String),
    Column("config_digest", String),
    Column("agent_version_id", Integer, ForeignKey("agent_versions.id")),
    Column("composition_snapshot", String),
    Column("rendered_prompt", String),
    Column("variables", String),
    Column("validation_status", String),
    Column("validation_errors", String),
    Column("schema_validated_via", String),
    Column("post_status", String),
    Column("post_errors", String),
    Column("conversation_format", String),
    Column("conversation_uri", String),
    Column("runner_profile_id", String, ForeignKey("runner_profiles.id")),
    Column("resource_snapshot", String),
    Column("mcp_snapshot", String),
    Column("runner_snapshot", String),
    Column("prompt_version_id", Integer, ForeignKey("prompt_versions.id"), nullable=True),
    Index("runs_by_agent", "agent_id", "created_at"),
    Index("runs_by_status", "status", "created_at"),
    Index("idx_runs_runner_profile_id", "runner_profile_id"),
)

usage = Table(
    "usage",
    metadata,
    Column("run_id", String, ForeignKey("runs.id"), primary_key=True),
    Column("model", String),
    Column("input_tokens", Integer, server_default="0"),
    Column("output_tokens", Integer, server_default="0"),
    Column("cache_read_tokens", Integer, server_default="0"),
    Column("cache_write_tokens", Integer, server_default="0"),
    Column("cost_usd", Float),
)

guardrail_results = Table(
    "guardrail_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, ForeignKey("runs.id"), nullable=False),
    Column("name", String, nullable=False),
    Column("ok", Integer, nullable=False),
    Column("message", String),
    Column("attempt", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    CheckConstraint("ok IN (0, 1)", name="guardrail_ok_bool"),
)

run_prompts = Table(
    "run_prompts",
    metadata,
    Column("run_id", String, ForeignKey("runs.id"), primary_key=True),
    Column("fragments", String, nullable=False),
    Column("created_at", String, nullable=False),
)

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
    Column("is_draft", Integer, nullable=False, server_default="0"),
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

webhook_deliveries = Table(
    "webhook_deliveries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, ForeignKey("runs.id"), nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("url", String, nullable=False),
    Column("payload_json", String),
    Column("response_status", Integer),
    Column("response_body", String),
    Column("latency_ms", Integer),
    Column("error", String),
    Column("ts", String, nullable=False),
    Index("idx_webhook_deliveries_run", "run_id"),
)

run_comments = Table(
    "run_comments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, ForeignKey("runs.id"), nullable=False),
    Column("author", String, nullable=False),
    Column("body", String, nullable=False),
    Column("created_at", String, nullable=False),
    Index("idx_run_comments_run", "run_id"),
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
    CheckConstraint("is_system_default IN (0, 1)", name="runner_profiles_is_system_default_bool"),
    Index("idx_runner_profiles_backend_provider", "backend", "provider"),
    Index("idx_runner_profiles_enabled", "is_enabled"),
)

agent_runner_profiles = Table(
    "agent_runner_profiles",
    metadata,
    Column("agent_id", String, primary_key=True),
    Column("runner_profile_id", String, ForeignKey("runner_profiles.id"), nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)

# --- Plan 01: central resource repository ---

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
    Column("pinned_version_id", String, ForeignKey("resource_versions.id"), nullable=True),
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
        "agent_id", "marker", "resource_id",
        name="uq_agent_prompt_bindings_triple",
    ),
    Index("ix_agent_prompt_bindings_agent", "agent_id"),
    Index(
        "uq_agent_prompt_bindings_slot",
        "agent_id", "slot",
        unique=True,
        sqlite_where=text("slot IS NOT NULL"),
    ),
)

# --- Validation contracts (rules + validators, reusable across agent versions) ---

validation_contracts = Table(
    "validation_contracts",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("rules", String, nullable=False, server_default="[]"),
    # validators: JSON list of {kind, ...} entries. The jsonschema
    # validator is implicit from the agent's output_schema binding and
    # is NOT listed here. Today the only explicit kind is 'http';
    # adding a new kind means extending the runtime dispatch in
    # core/run/validation.py — no migration needed.
    Column("validators", String, nullable=False, server_default="[]"),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    UniqueConstraint("name", name="uq_validation_contracts_name"),
)

agent_version_validation_bindings = Table(
    "agent_version_validation_bindings",
    metadata,
    Column(
        "agent_version_id",
        Integer,
        ForeignKey("agent_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("direction", String, nullable=False),
    Column(
        "contract_id",
        String,
        ForeignKey("validation_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    CheckConstraint(
        "direction IN ('input', 'output')",
        name="agent_version_validation_direction_check",
    ),
    UniqueConstraint(
        "agent_version_id", "direction", name="pk_agent_version_validation"
    ),
    Index(
        "ix_agent_version_validation_version", "agent_version_id"
    ),
    Index("ix_agent_version_validation_contract", "contract_id"),
)

# --- Plan 03: workspace file-materialize bindings ---

workspace_file_resource_bindings = Table(
    "workspace_file_resource_bindings",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("resource_id", String, ForeignKey("resources.id"), nullable=False),
    Column("target_path", String, nullable=True),
    Column("pinned_version_id", String, ForeignKey("resource_versions.id"), nullable=True),
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
        "workspace_id", "resource_id", "target_path",
        name="uq_workspace_file_bindings_triple",
    ),
    Index("ix_workspace_file_bindings_workspace", "workspace_id"),
)

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
    UniqueConstraint("workspace_id", "version_number", name="uq_workspace_env_doc_version"),
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
        "workspace_id", "server_name", "tool_name",
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
    Column("revoked_at", String, nullable=True),  # NULL = active; set to iso timestamp on revoke
    Column("revoked_by", String, nullable=True),
    Column("revoke_changelog", String, nullable=True),
    Index("ix_agent_tool_grants_agent", "agent_id"),
    UniqueConstraint("agent_id", "tool_name", name="uq_agent_tool_grant"),
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
    # 'manifest' = declared in agentbox.toml, 'db' = created via API only
    Column("source", String, nullable=False, server_default="db"),
    Column("created_at", String, nullable=False),
    Column("created_by", String, nullable=True),
    Column("updated_at", String, nullable=False),
    CheckConstraint(
        "source IN ('manifest', 'db')",
        name="workspaces_source_check",
    ),
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
    UniqueConstraint(
        "server_name", "config_hash", name="uq_mcp_discovery_server_hash"
    ),
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
