"""/api/activity endpoints — KPIs, time series, breakdowns, recent runs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query

from agentbox.api.deps import get_loader, get_store

router = APIRouter(prefix="/api/activity", tags=["activity"])

ActivityRange = Literal["7d", "30d", "90d"]


def _since(range_: ActivityRange) -> str:
    days = {"7d": 7, "30d": 30, "90d": 90}[range_]
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


@router.get("/summary")
def summary(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
) -> dict:
    return get_store().activity_summary(_since(range), agent=action)


@router.get("/runs")
def recent_runs(
    range: ActivityRange = Query(default="30d"),
    action: str | None = Query(default=None),
    executor: str | None = Query(default=None),
    state: Literal["running", "ok", "error"] | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> dict:
    state_map = {"ok": "ok", "running": "running", "error": "error"}
    rows = get_store().list_runs_rich(
        since_iso=_since(range),
        agent=action,
        status=state_map.get(state) if state else None,
        executor=executor,
        limit=limit,
    )
    # Compute duration on the fly so the client doesn't recompute.
    loader = get_loader()
    runner_kind_cache: dict[str, str | None] = {}

    def _runner_kind(agent_id: str) -> str | None:
        if agent_id not in runner_kind_cache:
            ad = loader.get(agent_id)
            runner_kind_cache[agent_id] = ad.runner.kind if ad else None
        return runner_kind_cache[agent_id]

    out = []
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
        out.append(
            {
                "id": r["id"],
                "action_name": r["agent_id"],
                "executor": _runner_kind(r["agent_id"]) or r["executor"],
                "model": r["executor"] if r["executor"] != "unknown" else None,
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


def _state_label(status: str) -> str:
    return {"ok": "succeeded", "error": "failed", "running": "running"}.get(
        status, status
    )
