"""Drop is_draft from prompt_versions (plan 148).

Revision ID: 0011_drop_prompt_versions_is_draft
Revises: 0010_output_schema_binding
Create Date: 2026-07-09 00:00:00.000000

The draft/publish two-step is removed from prompt versioning.
A prompt version is now just a version — no staging state.

Data migration: any rows with ``is_draft = 1`` are committed first
(``is_draft`` set to 0) so no content is lost, then the column is
dropped entirely.  Idempotent — if the column is already absent
(fresh DB) the operation is a no-op.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_drop_prompt_versions_is_draft"
down_revision: str | Sequence[str] | None = "0011_backfill_composition_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(conn: sa.engine.Connection, table: str, column: str) -> bool:
    """Return True if column exists in table (SQLite PRAGMA)."""
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "prompt_versions", "is_draft"):
        # Fresh DB — column was never added; nothing to do.
        return

    # 1. Commit any lingering draft rows so no content is lost.
    conn.execute(
        sa.text("UPDATE prompt_versions SET is_draft = 0 WHERE is_draft = 1")
    )

    # 2. Drop the column (SQLite: recreate table without it).
    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.drop_column("is_draft")


def downgrade() -> None:
    conn = op.get_bind()

    if _column_exists(conn, "prompt_versions", "is_draft"):
        return

    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_draft",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
