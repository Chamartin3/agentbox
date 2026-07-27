"""Drop the agent ``source_format`` column.

Revision ID: 0020_drop_agent_source_format
Revises: 0019_drop_workspace_env_vars
Create Date: 2026-08-02 00:00:00.000000

Agent ``source_format`` recorded which file format an agent was loaded from
(inline TOML, standalone TOML, markdown, bundle). Agents are now DB-only and
the field was vestigial — always ``None`` for anything created via the API,
CLI, or dashboard. This drops the column from ``agent_meta`` and
``agent_versions`` and strips the key from stored JSON snapshots.

The unrelated *conversation* ``source_format`` (transcript format) is a
different column on other tables and is untouched.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_drop_agent_source_format"
down_revision: str | Sequence[str] | None = "0019_drop_workspace_env_vars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(conn: sa.Connection, table: str, column: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Strip the key from stored JSON snapshots so nothing reads it back.
    if _has_column(conn, "agent_versions", "source_format"):
        rows = conn.execute(
            sa.text("SELECT id, config_json, content_snapshot FROM agent_versions")
        ).fetchall()
        for row in rows:
            m = row._mapping
            updates: dict[str, str] = {}
            for col in ("config_json", "content_snapshot"):
                raw = m[col]
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict) and "source_format" in data:
                    data.pop("source_format", None)
                    updates[col] = json.dumps(data)
            if updates:
                assignments = ", ".join(f"{k} = :{k}" for k in updates)
                conn.execute(
                    sa.text(f"UPDATE agent_versions SET {assignments} WHERE id = :id"),
                    {**updates, "id": m["id"]},
                )

    # 2. Drop the columns.
    if _has_column(conn, "agent_versions", "source_format"):
        with op.batch_alter_table("agent_versions") as batch:
            batch.drop_column("source_format")
    if _has_column(conn, "agent_meta", "source_format"):
        with op.batch_alter_table("agent_meta") as batch:
            batch.drop_column("source_format")


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_column(conn, "agent_meta", "source_format"):
        with op.batch_alter_table("agent_meta") as batch:
            batch.add_column(sa.Column("source_format", sa.String(), nullable=True))
    if not _has_column(conn, "agent_versions", "source_format"):
        with op.batch_alter_table("agent_versions") as batch:
            batch.add_column(
                sa.Column(
                    "source_format",
                    sa.String(),
                    nullable=False,
                    server_default="",
                )
            )
