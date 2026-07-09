"""Drop workspace_host_env_grants (grants moved to agent scope in 0007).

Revision ID: 0008_drop_workspace_host_env_grants
Revises: 0007_agent_host_env_grants
Create Date: 2026-07-07 00:00:00.000000

Host-env grants are now agent-owned (agent_host_env_grants). Data was copied
onto agents by 0007; the workspace-scoped table is dropped here. host_env_profiles
(shared bundles) are unaffected.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008_drop_workspace_host_env_grants"
down_revision: str | Sequence[str] | None = "0007_agent_host_env_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("workspace_host_env_grants")


def downgrade() -> None:
    op.create_table(
        "workspace_host_env_grants",
        sa.Column("workspace_id", sa.String(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(),
            sa.ForeignKey("host_env_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("overrides", sa.JSON(), nullable=True),
        sa.Column("changelog", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
    )
