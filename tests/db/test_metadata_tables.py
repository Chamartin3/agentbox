"""Snapshot the table set bound to the single ``MetaData``.

Plan 127 collapsed the Core ``schema/`` tables into the SQLModel entities;
``base.metadata`` (``SQLModel.metadata``) is now the one shared ``MetaData``.
Alembic inspects ``metadata.tables`` to autogenerate migrations and
``metadata.create_all(engine)`` runs at startup, so losing a table from the
shared instance silently breaks both. Lock the table set here so a future
entity move can't quietly drop one.
"""

from __future__ import annotations

import agentbox.core.db  # noqa: F401 — importing the facade registers every entity
from agentbox.core.db.base.metadata import metadata

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "active_agent_versions",
        "active_resource_versions",
        "agent_config_events",
        "agent_meta",
        "agent_prompt_resource_bindings",
        "agent_runner_profiles",
        "agent_sync",
        "agent_tool_grants",
        "agent_host_env_grants",
        "agent_version_comments",
        "agent_version_files",
        "agent_version_ratings",
        "agent_versions",
        "agents",
        "api_tokens",
        "managed_credentials",
        "host_env_call_log",
        "host_env_profiles",
        "mcp_tool_discovery_cache",
        "prompt_versions",
        "resource_blobs",
        "resource_versions",
        "resources",
        "run_comments",
        "run_prompts",
        "runner_profiles",
        "runs",
        "sessions",
        "settings",
        "usage",
        "webhook_deliveries",
        "workspace_env_doc_versions",
        "workspace_env_docs",
        "workspace_file_resource_bindings",
        "workspace_mcp_overrides",
        "workspace_mcp_policies",
        "workspace_mcp_tool_overrides",
        "workspace_runtime_permissions",
        "workspace_credentials",
        "workspace_subagents",
        "workspaces",
    }
)


def test_metadata_tables_match_expected() -> None:
    actual = frozenset(metadata.tables.keys())
    missing = EXPECTED_TABLES - actual
    extra = actual - EXPECTED_TABLES
    assert not missing, f"metadata lost tables: {sorted(missing)}"
    assert not extra, (
        f"metadata gained tables without updating this test: {sorted(extra)}"
    )
