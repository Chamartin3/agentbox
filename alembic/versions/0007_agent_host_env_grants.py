"""Agent-scoped host-env grants (workspace → agent ownership).

Revision ID: 0007_agent_host_env_grants
Revises: 0006_drop_workenv_templates
Create Date: 2026-07-07 00:00:00.000000

Authorization is agent territory: host-env grants move from
``workspace_host_env_grants`` (workspace-keyed) to a new agent-keyed
``agent_host_env_grants`` table. This is the additive half — the new table is
created and existing workspace grants are copied (permissively, one-way) onto
every agent bound to that workspace:

  - every subagent registered in ``workspace_subagents``, and
  - the agent whose id equals the workspace name (agent-as-workspace).

The old ``workspace_host_env_grants`` table is left in place until the read
paths are fully migrated. ``host_env_profiles`` (named grant bundles) are
shared and unchanged.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_agent_host_env_grants"
down_revision: str | Sequence[str] | None = "0006_drop_workenv_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_host_env_grants",
        sa.Column(
            "agent_id",
            sa.String(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
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
        if_not_exists=True,
    )

    # Copy workspace grants onto every bound subagent (INSERT OR IGNORE: the
    # agent-keyed PK dedups when an agent belongs to multiple sources).
    op.execute(
        """
        INSERT OR IGNORE INTO agent_host_env_grants
            (agent_id, profile_id, overrides, changelog, created_at, created_by)
        SELECT s.agent_id, g.profile_id, g.overrides, g.changelog,
               g.created_at, g.created_by
        FROM workspace_host_env_grants g
        JOIN workspace_subagents s ON s.workspace_id = g.workspace_id
        """
    )
    # ...and onto the agent-as-workspace (workspace name == agent id).
    op.execute(
        """
        INSERT OR IGNORE INTO agent_host_env_grants
            (agent_id, profile_id, overrides, changelog, created_at, created_by)
        SELECT g.workspace_id, g.profile_id, g.overrides, g.changelog,
               g.created_at, g.created_by
        FROM workspace_host_env_grants g
        JOIN agents a ON a.id = g.workspace_id
        """
    )


def downgrade() -> None:
    op.drop_table("agent_host_env_grants")
