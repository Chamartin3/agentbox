"""One-shot backfill: populate ``runs.prompt_version_id`` from history.

Strategy
--------
For each run with ``prompt_version_id IS NULL`` and a non-null
``agent_id`` + ``created_at``, find the latest ``prompt_versions`` row
for that agent whose ``created_at <= runs.created_at`` and assign it.

This is a best-effort migration — runs predating the prompt-versions
table simply remain NULL. The script is idempotent (only touches NULLs).

Usage
-----
::

    from agentbox.core.db import Database
    from agentbox.core.db.seeds.system import backfill

    db = Database(Path("path/to/agentbox.db"))
    n = backfill(db)
    print(f"updated {n} runs")
"""

from __future__ import annotations

from sqlalchemy import text

from agentbox.core.db.database import Database


def backfill(db: Database) -> int:
    """Run the backfill. Returns the number of rows updated."""
    sql = text(
        """
        UPDATE runs
        SET prompt_version_id = (
            SELECT pv.id
            FROM prompt_versions pv
            WHERE pv.agent_id = runs.agent_id
              AND pv.created_at <= runs.created_at
            ORDER BY pv.created_at DESC
            LIMIT 1
        )
        WHERE prompt_version_id IS NULL
          AND agent_id IS NOT NULL
          AND created_at IS NOT NULL
        """
    )
    with db.engine.begin() as conn:
        result = conn.execute(sql)
        return int(result.rowcount or 0)
