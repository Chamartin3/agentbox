"""Snapshot the table set bound to ``agentbox.core.db.metadata``.

Phase 3 of the consolidation plan moves schema definitions across domain
packages while keeping a single shared ``MetaData`` instance. Alembic
inspects ``metadata.tables`` to autogenerate migrations and
``metadata.create_all(engine)`` runs at startup, so losing a table from
the shared instance silently breaks both.

Lock the table set here so the split can't quietly drop one.
"""

from __future__ import annotations

from agentbox.core.db import metadata, schema
from agentbox.core.db._metadata import metadata as private

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
        "agent_version_comments",
        "agent_version_files",
        "agent_version_ratings",
        "agent_versions",
        "agents",
        "api_tokens",
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
        "shared_resources",
        "usage",
        "webhook_deliveries",
        "workspace_env_doc_versions",
        "workspace_env_docs",
        "workspace_file_resource_bindings",
        "workspace_host_env_grants",
        "workspace_mcp_overrides",
        "workspace_mcp_policies",
        "workspace_mcp_tool_overrides",
        "workspace_runtime_permissions",
        "workspace_subagents",
        "workspaces",
        "workenv_templates",
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


def test_metadata_is_shared_singleton() -> None:
    """The façade ``metadata`` must be the same object as ``_metadata.metadata``.

    If a domain ``schema.py`` ever instantiates its own ``MetaData()``,
    its tables silently won't appear in ``agentbox.core.db.metadata``
    — Alembic would miss them. This test catches that.
    """
    assert metadata is private


def test_shared_metadata_seen_by_legacy_schema_module() -> None:
    """Until Phase 6 deletes the monolith, the old ``schema.py`` is the
    canonical table location. Its ``metadata`` must be the shared one.
    """
    assert schema.metadata is metadata
