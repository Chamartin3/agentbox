"""Feedback domain types — shared across data and service layers."""

from datetime import UTC, datetime, timedelta
from typing import Literal

ActivityRange = Literal["7d", "30d", "90d"]


def since_iso(range_: ActivityRange) -> str:
    days = {"7d": 7, "30d": 30, "90d": 90}[range_]
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
