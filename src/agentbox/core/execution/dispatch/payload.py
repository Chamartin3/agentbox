"""Completion payload assembly from RunRecord and usage data.

The payload shape is channel-agnostic: no URLs, headers, or transport
specifics live here. Each dispatch channel receives the same payload and
pulls its own config from the channel spec.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, NotRequired, TypedDict

from agentbox.core.agents.validation import extract_json
from agentbox.core.data import RunRecord
from agentbox.core.data.payload_types import UsagePayload
from agentbox.core.execution.dispatch.policy import DispatchStore


class AgentEventPayload(TypedDict):
    """Payload for agent lifecycle event webhooks (publish/rollback)."""

    event: str
    agent_id: str
    version: int
    version_id: int
    reason: str
    published_at: str


class CompletionPayload(TypedDict):
    run_id: str
    agent_id: str
    session_id: str | None
    status: str
    output: Any
    output_structured: dict[str, Any] | list | None
    error: str | None
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    usage: UsagePayload | None
    validation_status: str | None
    schema_validated_via: str | None
    # Extra fields added by future channels without invalidating the shape.
    extra: NotRequired[dict[str, Any]]


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


def completion_payload(
    run: RunRecord,
    *,
    usage: UsagePayload | None,
    duration_ms: int | None,
) -> CompletionPayload:
    """Build a channel-agnostic completion payload for ``run``."""
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


def build_completion_payload(run: RunRecord, store: DispatchStore) -> CompletionPayload:
    """Build a completion payload with usage and duration populated."""
    usage = store.get_usage(run.id)
    duration_ms: int | None = None
    if run.created_at and run.finished_at:
        try:
            started = datetime.fromisoformat(run.created_at)
            ended = datetime.fromisoformat(run.finished_at)
            duration_ms = int((ended - started).total_seconds() * 1000)
        except (ValueError, TypeError):
            duration_ms = None
    return completion_payload(run, usage=usage, duration_ms=duration_ms)


__all__ = [
    "CompletionPayload",
    "build_completion_payload",
    "completion_payload",
]
