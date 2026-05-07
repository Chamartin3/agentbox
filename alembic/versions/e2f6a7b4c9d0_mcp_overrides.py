"""Add workspace MCP override tables.

Revision ID: e2f6a7b4c9d0
Revises: d1e5f6a3b7c8
Create Date: 2026-05-22 21:00:00.000000

Plan 05 — workspace-scoped MCP server + tool toggles with default policy.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f6a7b4c9d0"
down_revision: str | Sequence[str] | None = "d1e5f6a3b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_mcp_overrides",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("server_name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("config_overrides", sa.JSON(), nullable=True),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "server_name", name="uq_workspace_mcp_override"),
    )
    op.create_index(
        "ix_workspace_mcp_overrides_workspace",
        "workspace_mcp_overrides",
        ["workspace_id"],
    )
    op.create_table(
        "workspace_mcp_tool_overrides",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("server_name", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "server_name",
            "tool_name",
            name="uq_workspace_mcp_tool_override",
        ),
    )
    op.create_index(
        "ix_workspace_mcp_tool_overrides_workspace",
        "workspace_mcp_tool_overrides",
        ["workspace_id"],
    )
    op.create_table(
        "workspace_mcp_policies",
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column(
            "default_policy",
            sa.String(),
            nullable=False,
            server_default="allow_all_unless_disabled",
        ),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.add_column("runs", sa.Column("mcp_snapshot", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "mcp_snapshot")
    op.drop_table("workspace_mcp_policies")
    op.drop_index(
        "ix_workspace_mcp_tool_overrides_workspace",
        table_name="workspace_mcp_tool_overrides",
    )
    op.drop_table("workspace_mcp_tool_overrides")
    op.drop_index(
        "ix_workspace_mcp_overrides_workspace", table_name="workspace_mcp_overrides"
    )
    op.drop_table("workspace_mcp_overrides")
