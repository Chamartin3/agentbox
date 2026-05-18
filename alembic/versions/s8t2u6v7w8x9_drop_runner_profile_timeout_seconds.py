"""Drop runner_profiles.timeout_seconds.

Revision ID: s8t2u6v7w8x9
Revises: r7s1t5u6v7w8
Create Date: 2026-05-27 22:55:00.000000

Timeout is no longer a per-profile concern. It is read exclusively from
the agent's runner config and falls back to
``DEFAULT_RUNNER_TIMEOUT_SECONDS`` (1200s) when unset.

Removing the column closes the precedence ambiguity that allowed a
profile's default 120s to silently override an agent's configured value.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s8t2u6v7w8x9"
down_revision: str | Sequence[str] | None = "r7s1t5u6v7w8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runner_profiles") as batch:
        batch.drop_column("timeout_seconds")


def downgrade() -> None:
    with op.batch_alter_table("runner_profiles") as batch:
        batch.add_column(sa.Column("timeout_seconds", sa.Integer(), nullable=True))
