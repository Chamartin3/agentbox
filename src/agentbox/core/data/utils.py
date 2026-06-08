"""Non-domain utility functions used across the ``core.data`` package."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Return current UTC timestamp as an ISO 8601 string (second precision)."""
    return datetime.now(UTC).isoformat(timespec="seconds")
