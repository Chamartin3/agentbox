"""Drop the workspace_env_vars table.

Revision ID: 0019_drop_workspace_env_vars
Revises: 0018_workspace_credential_env_var_override
Create Date: 2026-07-31 00:00:00.000000

Per-workspace plaintext env vars were removed — workspaces now manage
everything as credentials (with per-workspace env-var-name remapping). The
table and its UI/API are gone; this drops the storage.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_drop_workspace_env_vars"
down_revision: str | Sequence[str] | None = "0018_workspace_credential_env_var_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("workspace_env_vars"):
        op.drop_table("workspace_env_vars")


def downgrade() -> None:
    op.create_table(
        "workspace_env_vars",
        sa.Column("workspace_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
