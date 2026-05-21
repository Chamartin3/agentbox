"""Drop validation_contracts.rules (Plan 22 Phase 3).

Revision ID: u0v4w8x9y0z1
Revises: t9u3v7w8x9y0
Create Date: 2026-05-31 13:00:00.000000

Plan 22 retires the floating contract-level ``rules[]``. Each validator
now carries its own ``description``, rendered as a Constraints bullet
in the system prompt. The one-time data migration that joined any
remaining ``rules[]`` into a validator description has already run
against the live DB; this revision removes the now-vestigial column.

Downgrade re-adds the column as nullable (server_default "[]") so an
older snapshot can still boot, but data is not reconstructed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u0v4w8x9y0z1"
down_revision: str | Sequence[str] | None = "t9u3v7w8x9y0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = sa.inspect(bind).get_columns(table)
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    if not _has_column("validation_contracts", "rules"):
        return
    with op.batch_alter_table("validation_contracts") as batch:
        batch.drop_column("rules")


def downgrade() -> None:
    if _has_column("validation_contracts", "rules"):
        return
    with op.batch_alter_table("validation_contracts") as batch:
        batch.add_column(
            sa.Column(
                "rules",
                sa.String(),
                nullable=False,
                server_default="[]",
            )
        )
