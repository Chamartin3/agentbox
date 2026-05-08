"""Add workspace_subagents table.

Revision ID: i8j2k4l6m3n5
Revises: h7i9j3k5l2m4
Create Date: 2026-05-23 20:30:00.000000

Stores subagent assignments per workspace. Each subagent is a composed
agent rendered into per-backend folders (.claude/agents/, .opencode/agents/,
etc.) at workspace materialize time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i8j2k4l6m3n5"
down_revision: str | Sequence[str] | None = "h7i9j3k5l2m4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_subagents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "alias", name="uq_workspace_subagents_alias"
        ),
    )
    op.create_index(
        "ix_workspace_subagents_workspace",
        "workspace_subagents",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_subagents_workspace", table_name="workspace_subagents"
    )
    op.drop_table("workspace_subagents")
