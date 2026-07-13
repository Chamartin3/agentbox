"""Envelope parsing and usage-event assembly for Claude Code output."""

from __future__ import annotations

from agentbox.core.data.jsontypes import JsonDict, JsonValue

import json
from typing import Any

from agentbox.core.data.events import UsageEvent


def _parse_envelope(raw: str) -> JsonDict | None:
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


def _build_usage_event(run_id: str, envelope: JsonDict) -> UsageEvent | None:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        return None
    model_usage = envelope.get("modelUsage")
    model_name: str | None = None
    if isinstance(model_usage, dict) and model_usage:
        model_name = next(iter(model_usage.keys()), None)
    return UsageEvent(
        run_id=run_id,
        input_tokens=_safe_int(usage.get("input_tokens")),
        output_tokens=_safe_int(usage.get("output_tokens")),
        cache_read_tokens=_safe_int(usage.get("cache_read_input_tokens")),
        cache_write_tokens=_safe_int(usage.get("cache_creation_input_tokens")),
        cost_usd=_safe_float(envelope.get("total_cost_usd")),
        model=model_name,
    )


def _safe_int(v: JsonValue) -> int:
    return int(v) if isinstance(v, (int, float)) else 0


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


__all__ = ["_build_usage_event", "_parse_envelope", "_safe_float"]
