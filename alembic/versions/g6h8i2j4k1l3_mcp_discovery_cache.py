"""Add MCP tool discovery cache table.

Revision ID: g6h8i2j4k1l3
Revises: e2f6a7b4c9d0
Create Date: 2026-05-23 12:00:00.000000

Plan 08 Phase 4 — SQLite-backed cache for MCP tool discovery results.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g6h8i2j4k1l3"
down_revision: str | Sequence[str] | None = "f3a7b8c5d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_discovery_cache",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("server_name", sa.String(), nullable=False),
        sa.Column("config_hash", sa.String(), nullable=False),
        sa.Column("tools_json", sa.String(), nullable=False),
        sa.Column("discovered_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "server_name", "config_hash", name="uq_mcp_discovery_cache"
        ),
    )
    op.create_index(
        "ix_mcp_discovery_cache_server",
        "mcp_tool_discovery_cache",
        ["server_name"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mcp_discovery_cache_server",
        table_name="mcp_tool_discovery_cache",
    )
    op.drop_table("mcp_tool_discovery_cache")
