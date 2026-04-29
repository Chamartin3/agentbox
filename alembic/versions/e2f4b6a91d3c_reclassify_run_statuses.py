"""Reclassify run statuses: split `error` into stopped/failed/error

Revision ID: e2f4b6a91d3c
Revises: d4e7b9a3c821
Create Date: 2026-05-22 16:00:00.000000

Historically every non-ok terminal status landed in ``error``. That
bucket conflated three very different outcomes:

- **Container/process died mid-run** (orphan-reaped runs).
- **Expected agent-level failure**: rate-limit / auth / quota error
  from the LLM provider, connection failure while submitting the
  response via webhook, or output schema validation rejection.
- **Genuine unexpected crash** in the executor or runner.

This migration backfills existing rows into the new status taxonomy
introduced alongside it (`stopped`, `failed`). The legacy `incomplete`
status — used by the second orphan reaper and the original webhook
delivery downgrade — is folded into `stopped` and `failed` respectively.

Backfill rules (applied in order, idempotent):

1. ``error LIKE '%orphaned%'`` (any status)         → ``stopped``
2. ``status='incomplete'`` AND not orphan-reaped     → ``failed``
   (the original incomplete-on-delivery-failure case)
3. ``status='error'`` AND error matches a known      → ``failed``
   expected-failure marker (rate-limit, validation, connection, auth)

Anything else stays as ``error``. The migration is safe to re-run.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e2f4b6a91d3c"
down_revision: Union[str, Sequence[str], None] = "d4e7b9a3c821"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Substring markers in ``runs.error`` that identify expected failures.
# Mirrors ``executor._FAILED_ERROR_MARKERS``; duplicated here so the
# migration stays self-contained.
_FAILED_MARKERS: tuple[str, ...] = (
    "rate limit",
    "rate-limit",
    "rate_limit",
    "ratelimit",
    " 429",
    "429:",
    "quota",
    "overloaded",
    "insufficient_quota",
    "FreeUsageLimitError",
    "CreditsError",
    "AI_APICallError",
    "AuthError",
    "UnauthorizedError",
    "invalid_api_key",
    "invalid api key",
    "authentication_error",
    "authentication error",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectTimeout",
    "ReadTimeout",
    "ECONNREFUSED",
    "ECONNRESET",
    "output validation failed",
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Orphan-reaped rows (any prior status) → stopped.
    bind.exec_driver_sql(
        """
        UPDATE runs
           SET status = 'stopped'
         WHERE error LIKE '%orphaned%'
           AND status IN ('error', 'incomplete')
        """
    )

    # 2) Remaining incomplete rows (webhook-delivery downgrade) → failed.
    bind.exec_driver_sql(
        "UPDATE runs SET status = 'failed' WHERE status = 'incomplete'"
    )

    # 3) error rows whose error text matches a known expected-failure
    #    marker → failed. Skip rows already moved to stopped above.
    like_clauses: list[str] = []
    params: dict[str, str] = {}
    for i, marker in enumerate(_FAILED_MARKERS):
        key = f"m{i}"
        like_clauses.append(f"error LIKE :{key}")
        params[key] = f"%{marker}%"
    where_marker = " OR ".join(like_clauses)
    bind.exec_driver_sql(
        f"""
        UPDATE runs
           SET status = 'failed'
         WHERE status = 'error'
           AND error IS NOT NULL
           AND ({where_marker})
        """,
        params,
    )


def downgrade() -> None:
    # Best-effort reverse: collapse the new statuses back into the old
    # error/incomplete buckets so a rollback restores schema-compatible
    # values. The original cause information lives in ``runs.error`` and
    # is preserved either way.
    bind = op.get_bind()
    bind.exec_driver_sql(
        "UPDATE runs SET status = 'incomplete' WHERE status = 'stopped'"
    )
    bind.exec_driver_sql(
        "UPDATE runs SET status = 'error' WHERE status = 'failed'"
    )
