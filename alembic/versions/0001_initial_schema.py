"""Initial schema (squashed baseline).

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-07 00:00:00.000000

Single squashed baseline. Replaces 30 historical migrations that were
collapsed when agentbox was extracted as a standalone library. The
schema is materialized directly from ``agentbox.core.db.schema``
(the SQLAlchemy metadata is the single source of truth), so there is
no hand-maintained DDL here to drift from the models.

Existing deployments that were past any prior revision must drop and
recreate their database before upgrading; there is no incremental
path across the squash boundary.
"""

from collections.abc import Sequence

from alembic import op

from agentbox.core.db import metadata

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind())
