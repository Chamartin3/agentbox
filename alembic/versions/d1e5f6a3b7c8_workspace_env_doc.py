"""Add workspace environment-instruction doc tables.

Revision ID: d1e5f6a3b7c8
Revises: c9d4a2b7e8f5
Create Date: 2026-05-22 20:30:00.000000

Plan 04 — structured env doc per workspace, versioned. Renders into
CLAUDE.md + AGENTS.md at run-prepare time.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e5f6a3b7c8"
down_revision: str | Sequence[str] | None = "c9d4a2b7e8f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_env_doc_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("is_draft", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "version_number"),
    )
    op.create_index(
        "ix_workspace_env_doc_versions_workspace_id",
        "workspace_env_doc_versions",
        ["workspace_id"],
    )
    op.create_table(
        "workspace_env_docs",
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("active_version_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("workspace_id"),
        sa.ForeignKeyConstraint(
            ["active_version_id"], ["workspace_env_doc_versions.id"], ondelete="SET NULL"
        ),
    )


def downgrade() -> None:
    op.drop_table("workspace_env_docs")
    op.drop_index(
        "ix_workspace_env_doc_versions_workspace_id",
        table_name="workspace_env_doc_versions",
    )
    op.drop_table("workspace_env_doc_versions")
