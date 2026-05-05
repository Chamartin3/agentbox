"""Null out runner_profiles.provider/model on incompatible backend pairs.

Revision ID: j9k3l5m7n4o6
Revises: i8j2k4l6m3n5
Create Date: 2026-05-23 21:00:00.000000

Plan 17: providers now declare ``compatible_backends``. Existing rows that
reference a provider the backend can't drive (e.g. claude_code + openai)
become invalid. This migration nulls out ``provider`` and ``model`` on
those rows so the next edit through the UI surfaces them as "incomplete"
rather than silently failing at run time.

The compatibility map is duplicated here intentionally — Alembic should
not import the application's provider registry, because that triggers
plugin loading and pulls in the FastAPI stack.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j9k3l5m7n4o6"
down_revision: str | Sequence[str] | None = "i8j2k4l6m3n5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirror of ProviderDescriptor.compatible_backends at the time of writing.
_COMPAT: dict[str, list[str]] = {
    "openai": ["token", "codex"],
    "anthropic": ["token", "claude_code"],
    "google": ["token"],
    "openrouter": ["token", "opencode"],
    "xai": ["token"],
    "ollama": ["token", "opencode"],
}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, backend, provider FROM runner_profiles "
            "WHERE provider IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        profile_id, backend, provider = row[0], row[1], row[2]
        compatible = _COMPAT.get(provider, [])
        if backend not in compatible:
            bind.execute(
                sa.text(
                    "UPDATE runner_profiles SET provider = NULL, model = NULL, "
                    "updated_at = :now WHERE id = :id"
                ),
                {"now": _now_iso(), "id": profile_id},
            )


def downgrade() -> None:
    # Lossy: we don't store the prior provider/model. No-op downgrade.
    pass


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
