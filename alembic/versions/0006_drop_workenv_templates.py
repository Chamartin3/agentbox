"""Drop workenv_templates — presets are subsumed by named workspaces.

Revision ID: 0006_drop_workenv_templates
Revises: 0005_add_workenv_templates
Create Date: 2026-07-06 00:00:00.000000

A "preset" is now just an existing workenv (workspace) loaded by name with
its bound resources (``load_workenv``). The separate ``workenv_templates``
snapshot table duplicated that concept and is removed.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_drop_workenv_templates"
down_revision: str | Sequence[str] | None = "0005_add_workenv_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("workenv_templates")


def downgrade() -> None:
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
