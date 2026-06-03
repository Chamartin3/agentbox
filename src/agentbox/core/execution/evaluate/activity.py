"""Activity / analytics service — enrichment over raw run rows."""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from agentbox.core.data import SessionStore

ActivityRange = Literal["7d", "30d", "90d"]


def since_iso(range_: ActivityRange) -> str:
    days = {"7d": 7, "30d": 30, "90d": 90}[range_]
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def _state_label(status: str) -> str:
    return {"ok": "succeeded", "error": "failed", "running": "running"}.get(
        status, status
    )


def enrich_recent_runs(
    store: SessionStore,
    *,
    range_: ActivityRange = "30d",
    agent: str | None = None,
    executor: str | None = None,
    state: Literal["running", "ok", "error"] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = store.list_runs_rich(
        since_iso=since_iso(range_),
        agent=agent,
        status=state,
        executor=executor,
        limit=limit,
    )

    profile_cache: dict[str, Any] = {}

    def _profile(profile_id: str | None) -> Any:
        if not profile_id:
            return None
        if profile_id in profile_cache:
            return profile_cache[profile_id]
        try:
            profile = store.get_runner_profile(profile_id)
        except Exception:
            profile = None
        profile_cache[profile_id] = profile
        return profile

    def _profile_attr(profile_id: str | None, attr: str) -> str | None:
        profile = _profile(profile_id)
        if profile is None:
            return None
        return getattr(profile, attr, None) or (
            profile.get(attr) if hasattr(profile, "get") else None
        )

    def _snapshot_fields(r: dict) -> tuple[str | None, str | None]:
        snap_raw = r.get("runner_snapshot")
        if snap_raw:
            try:
                snap = _json.loads(snap_raw) if isinstance(snap_raw, str) else snap_raw
                if isinstance(snap, dict):
                    return snap.get("backend"), snap.get("model")
            except (ValueError, TypeError):
                pass
        profile_id = r.get("runner_profile_id")
        return _profile_attr(profile_id, "backend"), _profile_attr(profile_id, "model")

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
        backend, configured_model = _snapshot_fields(r)
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
    return store.activity_summary(since_iso(range_), agent=agent)
