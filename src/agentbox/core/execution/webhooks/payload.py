"""Webhook payload assembly from RunRecord and usage data."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agentbox.core.data import RunRecord, RunStore
from agentbox.core.execution.output_validate import extract_json


def _parsed_output(run: RunRecord) -> Any:
    return run.output or ""


def _parsed_output_structured(run: RunRecord) -> dict[str, Any] | list | None:
    raw = run.output
    if not isinstance(raw, str) or not raw.strip():
        return None
    if run.validation_status != "ok":
        return None
    try:
        return json.loads(extract_json(raw))
    except (ValueError, TypeError):
        return None


def webhook_payload(
    run: RunRecord,
    *,
    usage: dict[str, Any] | None,
    duration_ms: int | None,
) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "session_id": run.session_id,
        "status": run.status,
        "output": _parsed_output(run),
        "output_structured": _parsed_output_structured(run),
        "error": run.error,
        "started_at": run.created_at,
        "finished_at": run.finished_at,
        "duration_ms": duration_ms,
        "usage": usage,
        "validation_status": run.validation_status,
        "schema_validated_via": run.schema_validated_via,
    }


def _build_payload(run: RunRecord, store: RunStore) -> dict[str, Any]:
    usage = store.get_usage(run.id)
    duration_ms: int | None = None
    if run.created_at and run.finished_at:
        try:
            started = datetime.fromisoformat(run.created_at)
            ended = datetime.fromisoformat(run.finished_at)
            duration_ms = int((ended - started).total_seconds() * 1000)
        except (ValueError, TypeError):
            duration_ms = None
    return webhook_payload(run, usage=usage, duration_ms=duration_ms)


__all__ = ["webhook_payload"]
