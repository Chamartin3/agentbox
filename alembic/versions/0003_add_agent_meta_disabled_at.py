"""Add agent_meta.disabled_at.

Revision ID: 0003_add_agent_meta_disabled_at
Revises: 0002_drop_guardrail_results
Create Date: 2026-06-22 00:00:00.000000

Adds a nullable timestamp column for a soft "disabled" marker — lighter
than soft-delete. Disabled agents remain visible in lists (opt-in via
``include_disabled``) but the run dispatcher refuses to invoke them.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_add_agent_meta_disabled_at"
down_revision: str | Sequence[str] | None = "0002_drop_guardrail_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ponytail: idempotent — metadata.create_all may have added the column
    # already when run against a fresh DB before alembic stamps.
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("agent_meta")}
    if "disabled_at" not in cols:
        op.add_column(
            "agent_meta",
            sa.Column("disabled_at", sa.String(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("agent_meta", "disabled_at")
