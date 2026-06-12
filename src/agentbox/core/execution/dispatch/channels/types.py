"""Shared value types for dispatch channels."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of a single dispatch delivery attempt."""

    ok: bool
    attempts: int
    last_error: str | None = None
    response_status: int | None = None


__all__ = ["DeliveryResult"]
