"""Add runs.runner_snapshot column.

Revision ID: p5q9r1s3t4u5
Revises: o4p8q0r2s9t3
Create Date: 2026-05-25 12:00:00.000000

Adds a JSON column that records the runner configuration resolved at
dispatch time (backend, model, timeout, provider, extra_args, plus any
inline overrides). Append-only — never updated after the run row is
written. Read by the UI and activity stream as the historical source
of truth so renaming/rebinding/deleting a profile no longer rewrites
what the run page displays.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p5q9r1s3t4u5"
down_revision: str | Sequence[str] | None = "o4p8q0r2s9t3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(runs)").fetchall()}
    if "runner_snapshot" in existing:
        return
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("runner_snapshot", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("runner_snapshot")
