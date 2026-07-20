"""Drop shared_resources table (plan 137).

Revision ID: 0009_drop_shared_resources
Revises: 0008_drop_workspace_host_env_grants
Create Date: 2026-07-09 00:00:00.000000

The shared_resources catalog was a superseded Plan-12 parallel resource
system with zero writers, zero readers, and zero references in agentbox or
in the sole embedder cv_agents. The SQLModel entity was deleted in plan 137
Phase B; this migration drops the table from existing databases.

The drop is idempotent (IF EXISTS) so it is safe on databases that never
had the table (e.g. fresh databases that skipped the create_all fallback).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_drop_shared_resources"
down_revision: str | Sequence[str] | None = "0008_drop_workspace_host_env_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shared_resources")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE shared_resources (
            id TEXT NOT NULL,
            version INTEGER NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            content TEXT,
            config_json TEXT,
            sha256 TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            author TEXT,
            changelog TEXT,
            tags TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (id, version)
        )
        """
    )
