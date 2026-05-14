"""Backfill agent_versions.config_json with execution/runtime/python sub-dicts.

Revision ID: q6r0s2t4u5v6
Revises: p5q9r1s3t4u5
Create Date: 2026-05-25 12:30:00.000000

Phase 2 of the runner-DB-as-source-of-truth refactor.

Reads each ``agent_versions`` row's existing snapshot (either
``config_json`` or, for legacy rows, ``content_snapshot``), extracts the
fields previously buried in ``runner`` that belong to the executor
(execution/runtime/python) and writes them back as named sub-dicts on
``config_json``. Runner-level fields (kind/model/timeout/extra_args)
are deliberately NOT touched — they continue to live on
``runner_profiles`` and the legacy ``runner`` block remains untouched
so the fallback path in ``agent_config.py`` keeps working until
Phase 4 removes ``AgentDef.runner`` entirely.

Idempotent: rows whose ``config_json`` already has all three sub-dicts
are skipped. Safe to re-run.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q6r0s2t4u5v6"
down_revision: str | Sequence[str] | None = "p5q9r1s3t4u5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _runner_value(runner_dict: dict, key: str, default):
    val = runner_dict.get(key)
    return val if val is not None else default


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, config_json, content_snapshot FROM agent_versions"
        )
    ).fetchall()

    for row in rows:
        vid, config_raw, content_raw = row[0], row[1], row[2]
        raw = config_raw or content_raw
        if not raw:
            continue
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue

        # Idempotency check
        existing_sections = (
            ("execution" in data)
            and ("runtime" in data)
            and ("python" in data)
        )
        if existing_sections:
            continue

        runner = data.get("runner") or {}
        if not isinstance(runner, dict):
            runner = {}

        if "execution" not in data:
            data["execution"] = {
                "max_validation_retries": int(
                    _runner_value(runner, "max_validation_retries", 0)
                ),
                "max_error_retries": int(
                    _runner_value(runner, "max_error_retries", 0)
                ),
                "output_validation_engine": _runner_value(
                    runner, "output_validation_engine", "both"
                ),
            }
        if "runtime" not in data:
            data["runtime"] = {
                "mcp_config_path": _runner_value(runner, "mcp_config_path", None),
                "allowed_tools": list(
                    _runner_value(runner, "allowed_tools", []) or []
                ),
            }
        if "python" not in data:
            data["python"] = {
                "agent_module": _runner_value(runner, "agent_module", None),
                "deps_factory": _runner_value(runner, "deps_factory", None),
                "output_schema_path": _runner_value(
                    runner, "output_schema_path", None
                ),
            }

        new_config = json.dumps(data, sort_keys=True)
        conn.execute(
            sa.text(
                "UPDATE agent_versions SET config_json = :cj WHERE id = :id"
            ),
            {"cj": new_config, "id": vid},
        )


def downgrade() -> None:
    # Not destructive — leaving the sub-dicts in place is harmless because
    # the legacy `runner` block is still authoritative for backwards-compat.
    pass
