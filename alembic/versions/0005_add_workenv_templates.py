"""Add workenv_templates table for WorkenvConfig presets.

Revision ID: 0005_add_workenv_templates
Revises: 0004_drop_agent_versions_is_draft
Create Date: 2026-06-22 00:00:00.000000

Adds a single ``workenv_templates`` table that stores named, reusable
WorkenvConfig snapshots as JSON blobs alongside the engine (recipe) they
target.  This is the storage layer for ``workspaces/generation/``
presets (Phase G of Plan 30).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_add_workenv_templates"
down_revision: str | Sequence[str] | None = "0004_drop_agent_versions_is_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workenv_templates",
        sa.Column("name", sa.String(), primary_key=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("engine", sa.String(), nullable=False, server_default="claude"),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("workenv_templates")
