"""Add workspace_credentials.env_var_override.

Revision ID: 0018_workspace_credential_env_var_override
Revises: 0017_workspace_env_vars
Create Date: 2026-07-31 00:00:00.000000

Per-workspace remap: expose an enabled credential's secret under a chosen
env-var name instead of the credential's default (e.g. token "DS1" →
DEEPSEEK_API_KEY in one workspace, "DS2" → DEEPSEEK_API_KEY in another).
NULL means use the credential's default env-var name.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_workspace_credential_env_var_override"
down_revision: str | Sequence[str] | None = "0017_workspace_env_vars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # idempotent — create_all may have added the column already on a fresh DB
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("workspace_credentials")}
    if "env_var_override" not in cols:
        op.add_column(
            "workspace_credentials",
            sa.Column("env_var_override", sa.String(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("workspace_credentials", "env_var_override")
