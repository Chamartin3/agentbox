"""/api/activity endpoints — KPIs, time series, breakdowns, recent runs."""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query

from agentbox.api.deps import get_store

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
    store = get_store()
    profile_backend_cache: dict[str, str | None] = {}

    def _backend_from_profile(profile_id: str | None) -> str | None:
        if not profile_id:
            return None
        if profile_id in profile_backend_cache:
            return profile_backend_cache[profile_id]
        try:
            profile = store.get_runner_profile(profile_id)
        except Exception:
            profile = None
        backend = None
        if profile is not None:
            backend = (
                getattr(profile, "backend", None)
                or (profile.get("backend") if hasattr(profile, "get") else None)
            )
        profile_backend_cache[profile_id] = backend
        return backend

    def _model_from_profile(profile_id: str | None) -> str | None:
        if not profile_id:
            return None
        try:
            profile = store.get_runner_profile(profile_id)
        except Exception:
            profile = None
        if profile is not None:
            return (
                getattr(profile, "model", None)
                or (profile.get("model") if hasattr(profile, "get") else None)
            )
        return None

    def _snapshot_fields(r: dict) -> tuple[str | None, str | None]:
        """Return (backend, configured_model) from snapshot or profile fallback."""
        snap_raw = r.get("runner_snapshot")
        if snap_raw:
            try:
                snap = _json.loads(snap_raw) if isinstance(snap_raw, str) else snap_raw
                if isinstance(snap, dict):
                    return snap.get("backend"), snap.get("model")
            except (ValueError, TypeError):
                pass
        # Pre-snapshot rows: fall back to the bound profile.
        profile_id = r.get("runner_profile_id")
        return _backend_from_profile(profile_id), _model_from_profile(profile_id)

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


def _state_label(status: str) -> str:
    return {"ok": "succeeded", "error": "failed", "running": "running"}.get(
        status, status
    )
