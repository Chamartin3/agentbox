"""Add agent_versions.workspace_name — FK-checked mirror of the config workspace ref.

Nullable column (NULL = no named workspace → default). Declared FOREIGN KEY to
``workspaces.name``; not enforced until the global SQLite ``foreign_keys``
pragma is enabled (blocked today by pre-existing violations elsewhere).

Backfill: copy the config's ``workspace`` into the column only when it names an
existing workspace; dangling/absent refs stay NULL so the column never holds a
phantom workspace.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0015_agent_version_workspace_fk"
down_revision: str | Sequence[str] | None = "0014_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: the column may already exist (fresh DBs materialize it from
    # entity metadata via create_all). Only add it when missing, but always run
    # the backfill so pre-existing rows get populated.
    conn = op.get_bind()
    cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(agent_versions)")]
    if "workspace_name" not in cols:
        op.add_column(
            "agent_versions",
            sa.Column(
                "workspace_name",
                sa.String(),
                sa.ForeignKey("workspaces.name"),
                nullable=True,
            ),
        )
    # Backfill valid refs only; dangling / absent → NULL (falls to default).
    op.execute(
        """
        UPDATE agent_versions
        SET workspace_name = json_extract(config_json, '$.workspace')
        WHERE json_valid(config_json)
          AND json_extract(config_json, '$.workspace') IN (SELECT name FROM workspaces)
        """
    )


def downgrade() -> None:
    op.drop_column("agent_versions", "workspace_name")
