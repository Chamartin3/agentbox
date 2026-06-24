"""Feedback analytics service helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agentbox.core.service.evaluation.service import EvaluationService
from agentbox.core.db import SessionStore
from agentbox.core.db.feedback.snapshots import snapshot_fields
from agentbox.core.db.feedback.types import ActivityRange, since_iso


def _state_label(status: str) -> str:
    return {"ok": "succeeded", "error": "failed", "running": "running"}.get(
        status, status
    )


def success_rate(total: int, failures: int) -> float:
    """Return the success rate as a float between 0.0 and 1.0."""
    return ((total - failures) / total) if total else 0.0


def enrich_recent_runs(
    store: SessionStore,
    *,
    range_: ActivityRange = "30d",
    agent: str | None = None,
    executor: str | None = None,
    state: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = EvaluationService().list_runs_rich(
        since_iso=since_iso(range_),
        agent=agent,
        status=state,
        executor=executor,
        limit=limit,
    )

    cache: dict[str, Any] = {}

    out: list[dict[str, Any]] = []
    for r in rows:
        started = r["created_at"]
        finished = r["finished_at"]
        duration_ms = None
        if finished:
            duration_ms = int(
                (
                    datetime.fromisoformat(finished).timestamp()
                    - datetime.fromisoformat(started).timestamp()
                )
                * 1000
            )
        backend, configured_model = snapshot_fields(store, cache, r)
        reported = r.get("reported_model")
        out.append(
            {
                "id": r["id"],
                "action_name": r["agent_id"],
                "backend": backend or reported or "unknown",
                "configured_model": configured_model,
                "reported_model": reported if reported != "unknown" else None,
                "state": _state_label(r["status"]),
                "started_at": started,
                "completed_at": finished,
                "duration_ms": duration_ms,
                "input_tokens": r.get("input_tokens"),
                "output_tokens": r.get("output_tokens"),
                "cache_read_tokens": r.get("cache_read_tokens"),
                "cache_creation_tokens": r.get("cache_creation_tokens"),
                "cost_usd": r.get("cost_usd"),
                "error": r.get("error"),
                "session_id": r.get("session_id"),
            }
        )
    return {"results": out, "total": len(out)}


def summary(
    store: SessionStore,
    *,
    range_: ActivityRange = "30d",
    agent: str | None = None,
) -> dict[str, Any]:
    return EvaluationService().activity_summary(since_iso(range_), agent=agent)


def aggregate_usage(*, store: SessionStore) -> dict:
    """Total tokens + cost across all runs."""
    return EvaluationService().aggregate_usage()


def activity_summary(*, store: SessionStore, since: str, agent_id: str | None = None) -> dict:
    """Roll up runs since ``since`` (ISO-8601) into totals + breakdowns."""
    return EvaluationService().activity_summary(since, agent=agent_id)


def distinct_executors(*, store: SessionStore) -> list[str]:
    """Distinct executor/model names across all recorded runs."""
    return EvaluationService().distinct_executors()
