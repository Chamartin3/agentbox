"""Envelope parsing and usage-event assembly for Claude Code output."""

from __future__ import annotations

import json
from typing import Any

from agentbox.core.db import UsageEvent


def _parse_envelope(raw: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of claude's stdout."""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    start = raw.find("{")
    if start < 0:
        return None
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError:
        return None


def _build_usage_event(run_id: str, envelope: dict[str, Any]) -> UsageEvent | None:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        return None
    model_usage = envelope.get("modelUsage")
    model_name: str | None = None
    if isinstance(model_usage, dict) and model_usage:
        model_name = next(iter(model_usage.keys()), None)
    return UsageEvent(
        run_id=run_id,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cost_usd=_safe_float(envelope.get("total_cost_usd")),
        model=model_name,
    )


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


__all__ = ["_build_usage_event", "_parse_envelope", "_safe_float"]
