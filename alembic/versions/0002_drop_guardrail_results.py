"""Drop guardrail_results table.

Revision ID: 0002_drop_guardrail_results
Revises: 0001_initial
Create Date: 2026-06-07 00:00:00.000000

The guardrails feature was removed (plan 25). The guardrail_results
table stored advisory post-run observational check results. No
built-in guardrails shipped; the data is not load-bearing for any
user-facing feature.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_drop_guardrail_results"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS guardrail_results")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE guardrail_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(id),
            name TEXT NOT NULL,
            ok INTEGER NOT NULL CHECK (ok IN (0, 1)),
            message TEXT,
            attempt INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
