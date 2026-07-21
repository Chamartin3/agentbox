"""Backfill composition blocks for inline-prompt agents (plan 147).

Revision ID: 0011_backfill_composition_blocks
Revises: 0010_output_schema_binding
Create Date: 2026-07-09 00:00:00.000000

Every ``agent_versions`` row whose ``config_json`` has no ``"composition"``
key is an "inline-prompt" agent — the prompt was stored in ``config_json``
as a top-level ``"prompt"`` field and the compose pipeline's Stage-1 gate
(``if agent.composition is not None and variables is not None``) was never
triggered.

After plan 147 the Stage-1 gate is the *only* path.  This migration
backfills each such row with a minimal ``composition`` block so Stage 1
always triggers after upgrade.

The minimal block is:

    {
        "system": "prompts/system.md",
        "references": [],
        "user_template": null,
        "input_schema": null,
        "output_schema": null,
        "transport": "system_message",
        "output_validation": "strict"
    }

These are the ``CompositionConfig`` defaults.  At runtime
``BindingsBundleSource.read_system()`` always reads from
``agent_versions.prompt_content`` and ignores ``composition.system``, so
the path value is irrelevant — the block only needs to be *present*.

Idempotency
-----------
- Rows that already have a ``composition`` key in ``config_json`` are
  skipped.
- Rows with ``config_json IS NULL`` are skipped (legacy rows without a
  config snapshot).

Downgrade
---------
Removes the ``composition`` key from each row this migration touched
(identified by the ``__composition_backfill__`` sentinel marker set in
``config_json`` by the upgrade step).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_backfill_composition_blocks"
down_revision: str | Sequence[str] | None = "0010_output_schema_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

# The sentinel key lets downgrade identify rows this migration touched.
_SENTINEL = "__composition_backfill__"

_DEFAULT_COMPOSITION = {
    "system": "prompts/system.md",
    "references": [],
    "user_template": None,
    "input_schema": None,
    "output_schema": None,
    "transport": "system_message",
    "output_validation": "strict",
}


def upgrade() -> None:
    conn = op.get_bind()

    # Fetch all rows that have config_json but no composition key.
    rows = conn.execute(
        sa.text(
            """
            SELECT id, config_json
            FROM agent_versions
            WHERE config_json IS NOT NULL
              AND json_extract(config_json, '$.composition') IS NULL
            """
        )
    ).fetchall()

    updated = 0
    for row in rows:
        version_id: int = row[0]
        raw: str = row[1]
        try:
            cfg = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning(
                "agent_versions id=%s: could not parse config_json — skipping",
                version_id,
            )
            continue

        if "composition" in cfg:
            # Paranoia check — already has composition; skip.
            continue

        cfg["composition"] = {**_DEFAULT_COMPOSITION, _SENTINEL: True}
        conn.execute(
            sa.text(
                "UPDATE agent_versions SET config_json = :cfg WHERE id = :vid"
            ),
            {"cfg": json.dumps(cfg, sort_keys=True), "vid": version_id},
        )
        updated += 1

    logger.info(
        "0011_backfill_composition_blocks: backfilled %d agent_version rows",
        updated,
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Find rows we touched (they carry the sentinel marker).
    rows = conn.execute(
        sa.text(
            """
            SELECT id, config_json
            FROM agent_versions
            WHERE config_json IS NOT NULL
              AND json_extract(config_json, :sentinel_path) = 1
            """,
        ),
        {"sentinel_path": f"$.composition.{_SENTINEL}"},
    ).fetchall()

    for row in rows:
        version_id: int = row[0]
        raw: str = row[1]
        try:
            cfg = json.loads(raw)
        except (ValueError, TypeError):
            continue
        cfg.pop("composition", None)
        conn.execute(
            sa.text(
                "UPDATE agent_versions SET config_json = :cfg WHERE id = :vid"
            ),
            {"cfg": json.dumps(cfg, sort_keys=True), "vid": version_id},
        )
