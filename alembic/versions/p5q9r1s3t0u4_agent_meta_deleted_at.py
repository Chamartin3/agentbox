"""Add agent_meta.deleted_at + flip sync_mode/export_to_disk defaults.

Revision ID: p5q9r1s3t0u4
Revises: o4p8q0r2s9t3
Create Date: 2026-05-25 12:00:00.000000

Plan 18 — DB-only config surface:
- ``DELETE /api/agents/{id}`` marks agents deleted via ``deleted_at``
  (we soft-delete; version history is retained).
- New agents default to ``sync_mode='off'`` and ``export_to_disk=0`` so
  filesystem changes never silently overwrite DB state. Existing rows
  keep their current values to avoid surprising long-running installs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p5q9r1s3t0u4"
down_revision: str | Sequence[str] | None = "q6r0s2t4u5v6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_meta") as batch:
        batch.add_column(sa.Column("deleted_at", sa.String(), nullable=True))
        batch.alter_column(
            "sync_mode", existing_type=sa.String(), server_default="off"
        )
        batch.alter_column(
            "export_to_disk", existing_type=sa.Integer(), server_default="0"
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_meta") as batch:
        batch.alter_column(
            "export_to_disk", existing_type=sa.Integer(), server_default="1"
        )
        batch.alter_column(
            "sync_mode", existing_type=sa.String(), server_default="watch"
        )
        batch.drop_column("deleted_at")
