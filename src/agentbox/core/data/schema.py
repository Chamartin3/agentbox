"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
startup via `_metadata.create_all(engine)`; no migration tool is used.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()

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
    Index("runs_by_agent", "agent_id", "created_at"),
    Index("runs_by_status", "status", "created_at"),
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
    Column("sync_mode", String, nullable=False, server_default="watch"),
    Column("export_to_disk", Integer, nullable=False, server_default="1"),
    Column("source_path", String, nullable=True),
    Column("source_format", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
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
