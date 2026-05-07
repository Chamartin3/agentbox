"""Add host-env profiles + workspace grants.

Revision ID: f3a7b8c5d1e2
Revises: e2f6a7b4c9d0
Create Date: 2026-05-22 21:30:00.000000

Plan 06 — host-environment MCP server data model.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a7b8c5d1e2"
down_revision: str | Sequence[str] | None = "e2f6a7b4c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "host_env_profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("grants", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_host_env_profile_name"),
    )
    op.create_table(
        "workspace_host_env_grants",
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=True),
        sa.Column("overrides", sa.JSON(), nullable=True),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("workspace_id"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["host_env_profiles.id"], ondelete="SET NULL"
        ),
    )
    op.create_table(
        "host_env_call_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("capability", sa.String(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_host_env_call_log_run", "host_env_call_log", ["run_id"])
    op.create_index(
        "ix_host_env_call_log_workspace", "host_env_call_log", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_host_env_call_log_workspace", table_name="host_env_call_log")
    op.drop_index("ix_host_env_call_log_run", table_name="host_env_call_log")
    op.drop_table("host_env_call_log")
    op.drop_table("workspace_host_env_grants")
    op.drop_table("host_env_profiles")
