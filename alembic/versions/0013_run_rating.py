"""Add a nullable ``rating`` column to ``runs`` (0-5 star run rating).

Revision ID: 0013_run_rating
Revises: 0012_drop_prompt_versions_is_draft
Create Date: 2026-07-29 00:00:00.000000

One rating per run, set from the run detail / runs list UI. Nullable —
an unrated run is NULL. Idempotent: skipped if the column already exists.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_run_rating"
down_revision: str | Sequence[str] | None = "0012_drop_prompt_versions_is_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(conn: sa.engine.Connection, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "runs", "rating"):
        return
    with op.batch_alter_table("runs") as batch_op:
        batch_op.add_column(sa.Column("rating", sa.Integer(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "runs", "rating"):
        return
    with op.batch_alter_table("runs") as batch_op:
        batch_op.drop_column("rating")
