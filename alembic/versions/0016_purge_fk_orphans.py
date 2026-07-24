"""Make the DB FK-clean so global SQLite foreign-key enforcement can be enabled.

FK enforcement (``PRAGMA foreign_keys``) was off historically, so two kinds of
inconsistency accumulated:

  1. Agents were only materialized as ``agent_versions`` / ``agent_meta`` rows —
     the canonical ``agents`` identity row was never written. Their tool /
     host-env grants therefore looked orphaned. We RESCUE these by backfilling
     the missing ``agents`` rows from ``agent_versions`` (no data loss).
  2. Genuinely dangling children (e.g. a binding to a deleted runner profile).
     We delete every row that still fails ``PRAGMA foreign_key_check``, looping
     until the DB is FK-clean.

Generic + idempotent: on an already-clean (or fresh) DB it does nothing.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_purge_fk_orphans"
down_revision: str | Sequence[str] | None = "0015_agent_version_workspace_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MAX_PASSES = 50  # bounded backstop; each pass strictly shrinks the orphan set


def upgrade() -> None:
    conn = op.get_bind()

    # (1) Rescue: materialize the canonical identity row for every agent that
    # only ever existed as versions, so its grants stop looking orphaned.
    conn.exec_driver_sql(
        """
        INSERT INTO agents (id, name, created_at)
        SELECT agent_id, agent_id, MIN(created_at)
        FROM agent_versions
        WHERE agent_id NOT IN (SELECT id FROM agents)
        GROUP BY agent_id
        """
    )

    # (2) Delete whatever is still genuinely orphaned.
    for _ in range(_MAX_PASSES):
        # (table, rowid, parent, fkid) per violating child row.
        violations = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if not violations:
            break
        for table, rowid, _parent, _fkid in violations:
            if rowid is None:
                continue  # WITHOUT ROWID table — none in this schema
            # table from schema metadata, rowid coerced to int — safe to inline.
            conn.exec_driver_sql(f'DELETE FROM "{table}" WHERE rowid = {int(rowid)}')


def downgrade() -> None:
    # Deleting orphaned rows is not reversible; nothing to undo.
    pass
