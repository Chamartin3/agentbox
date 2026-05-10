"""Add canonical workspaces registry table.

Revision ID: n3o7p9q1r8s2
Revises: m2n6o8p0q7r9
Create Date: 2026-05-24 21:00:00.000000

Until now there was no canonical "workspaces" table — workspace identity
was implicit, derived from a union of: agentbox.toml [[workspaces]],
on-disk directories under workspaces/, and any satellite DB table
keyed by workspace_id (env-docs, MCP overrides, file bindings,
host-env grants, runtime permissions, subagents).

That meant phantom workspaces never went away: deleting the manifest
entry left orphan rows that kept the name visible in the UI forever,
and there was no DELETE endpoint to clean them up.

This migration creates the canonical registry and backfills it with
every workspace name that the union currently produces so existing
deployments don't lose any rows.
"""
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "n3o7p9q1r8s2"
down_revision: str | Sequence[str] | None = "m2n6o8p0q7r9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SATELLITE_TABLES = (
    "workspace_subagents",
    "workspace_mcp_overrides",
    "workspace_mcp_tool_overrides",
    "workspace_mcp_policies",
    "workspace_host_env_grants",
    "workspace_env_docs",
    "workspace_file_resource_bindings",
    "workspace_runtime_permissions",
)


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="db"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
        sa.CheckConstraint(
            "source IN ('manifest', 'db')", name="workspaces_source_check"
        ),
    )

    # Backfill: union all workspace_id values from satellite tables.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    now = datetime.now(timezone.utc).isoformat()
    seen: set[str] = set()
    for table in _SATELLITE_TABLES:
        if table not in existing:
            continue
        rows = bind.execute(
            sa.text(f"SELECT DISTINCT workspace_id FROM {table}")
        ).fetchall()
        for (name,) in rows:
            if name and name not in seen:
                seen.add(name)
    for name in seen:
        bind.execute(
            sa.text(
                "INSERT INTO workspaces (name, source, created_at, updated_at) "
                "VALUES (:name, 'db', :now, :now)"
            ),
            {"name": name, "now": now},
        )


def downgrade() -> None:
    op.drop_table("workspaces")
