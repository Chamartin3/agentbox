"""Drop agent_versions.is_draft.

Revision ID: 0004_drop_agent_versions_is_draft
Revises: 0003_add_agent_meta_disabled_at
Create Date: 2026-06-22 00:00:00.000000

After Phase A introduced ``agent_meta.disabled_at``, the ``is_draft`` flag
on ``agent_versions`` became redundant: every save creates a new immutable
row, and the ``active_agent_versions`` pointer alone determines what runs
see. The flag is just a label — remove it.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_drop_agent_versions_is_draft"
down_revision: str | Sequence[str] | None = "0003_add_agent_meta_disabled_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ponytail: idempotent — schema/agents.py no longer declares is_draft, so
    # metadata.create_all against a fresh DB won't create it. Skip the drop if
    # it isn't there.
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("agent_versions")}
    if "is_draft" not in cols:
        return
    # SQLite needs batch_alter_table for DROP COLUMN.
    with op.batch_alter_table("agent_versions") as batch:
        batch.drop_column("is_draft")


def downgrade() -> None:
    with op.batch_alter_table("agent_versions") as batch:
        batch.add_column(
            sa.Column(
                "is_draft",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
