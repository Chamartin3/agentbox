"""Per-workspace shell environment variables.

Revision ID: 0017_workspace_env_vars
Revises: 0016_purge_fk_orphans
Create Date: 2026-07-30 00:00:00.000000

The ``WorkspaceEnvVar`` model (``core/db/workspaces/env_var.py``) shipped
without a migration, so ``workspace_env_vars`` was queried at run time but
never created — every run 500'd with ``no such table: workspace_env_vars``.
This additive table backfills it. One ``KEY=VALUE`` row per workspace,
injected into the agent subprocess at run time (plaintext config, not
secrets — those go through Credentials).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0017_workspace_env_vars"
down_revision: str | Sequence[str] | None = "0016_purge_fk_orphans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_env_vars",
        sa.Column("workspace_id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("workspace_env_vars")
