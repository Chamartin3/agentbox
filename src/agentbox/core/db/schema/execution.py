"""SQLAlchemy Core table definitions for the agentbox SQLite store.

Single source of truth for the persistence schema. Tables are created on
Alembic is the primary migration tool; metadata.create_all(engine) is the fallback.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
)

from agentbox.core.constants import ResourceType
from agentbox.core.db._metadata import metadata

_RESOURCE_TYPES_SQL = ", ".join(f"'{t.value}'" for t in ResourceType)

"""Run lifecycle tables: sessions, runs, usage, prompts, comments, webhooks."""

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
    Column(
        "prompt_version_id", Integer, ForeignKey("prompt_versions.id"), nullable=True
    ),
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

run_prompts = Table(
    "run_prompts",
    metadata,
    Column("run_id", String, ForeignKey("runs.id"), primary_key=True),
    Column("fragments", String, nullable=False),
    Column("created_at", String, nullable=False),
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
