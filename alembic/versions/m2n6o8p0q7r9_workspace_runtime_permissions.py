"""Add workspace_runtime_permissions overlay table.

Revision ID: m2n6o8p0q7r9
Revises: l1m5n7o9p6q8
Create Date: 2026-05-24 19:00:00.000000

Workspace runtime permissions (built-in tools, file scopes, max_tokens,
allow_file_write, allow_network) move from disk capabilities.json to a
DB overlay over WorkspaceDef defaults. Same pattern as
workspace_mcp_overrides over manifest.mcp_servers. capabilities.json
becomes a derived artifact written during config generation only.

allowed_tools (MCP tools) is NOT stored here — it is derived from
workspace_mcp_tool_overrides + workspace_mcp_policies at read time.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m2n6o8p0q7r9"
down_revision: str | Sequence[str] | None = "l1m5n7o9p6q8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_runtime_permissions",
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("allowed_builtin_tools", sa.JSON(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("allow_file_write", sa.Integer(), nullable=True),
        sa.Column("allow_network", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("workspace_runtime_permissions")
