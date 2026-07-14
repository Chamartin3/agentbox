"""EvaluationService — run/agent analytics (plan 093).

The read-only analytics domain: usage & cost aggregates, activity summaries,
paginated/rich run listings, filtered stats, and runner-profile stats.
Self-wiring like every ``Service``; owns no writes.

Analytics is query-centric: the aggregate SQL (and its natural row shaping)
lives on the Data layer — ``RunManager`` (run-centric, joins usage/agent_versions),
``UsageManager`` (usage aggregates), and ``RunnerProfileManager`` (profile stats).
This service orchestrates them; payload composition and field normalization
are service policy.

ponytail: analytics returns are nested ``dict`` response shapes; a full
TypedDict pass over them is deferred (tracked with plan 094's typing work).
"""
from __future__ import annotations

import json as _json
from datetime import datetime
from agentbox.core.data.payload_types import EnrichedRunRow, EnrichedRunsResult
from agentbox.core.data.profiles import RunnerProfile, RunnerProfileStats
from agentbox.core.data.rows import (
    ActivitySummaryRow,
    RichRunRow,
    RunPagedRow,
    RunStatsRow,
    UsageSummaryRow,
)
from agentbox.core.data.feedback import ActivityRange, since_iso
from agentbox.core.service.base import Service


class EvaluationService(Service):
    """Run/agent analytics — usage, cost, activity, stats, listings."""

    def __init__(self) -> None:
        super().__init__()
        self._runs = self._db.runs
        self._usage = self._db.usage
        self._profiles = self._db.runner_profiles

    # ── Usage aggregates ──────────────────────────────────────────────

    def aggregate_usage(self) -> UsageSummaryRow:
        """Total tokens + cost across all runs."""
        return self._usage.aggregate_usage()

    def distinct_executors(self) -> list[str]:
        """Distinct reported model values for filter UI."""
        return self._usage.distinct_executors()

    def distinct_agent_ids(self) -> list[str]:
        """Distinct agent_id values for filter UI."""
        return self._runs.distinct_agent_ids()

    # ── Activity / time-series ─────────────────────────────────────────

    def activity_summary(self, since_iso_str: str, agent: str | None = None) -> ActivitySummaryRow:
        """Roll up runs in a date range into /activity endpoint shape."""
        return self._runs.activity_summary(since_iso_str, agent)

    # ── Filtered stats ────────────────────────────────────────────────

    def stats_for_filters(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        agent_version: int | None = None,
        q: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
    ) -> RunStatsRow:
        """Aggregate stats matching the list_runs_paged filter set."""
        return self._runs.stats_for_filters(
            agent_id=agent_id,
            status=status,
            executor=executor,
            agent_version=agent_version,
            q=q,
            since_iso=since_iso,
            until_iso=until_iso,
        )

    # ── Run listings ──────────────────────────────────────────────────

    def list_runs_paged(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        agent_version: int | None = None,
        q: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RunPagedRow], int]:
        """Paginated + filterable run listing."""
        return self._runs.list_runs_paged(
            agent_id=agent_id,
            status=status,
            executor=executor,
            agent_version=agent_version,
            q=q,
            since_iso=since_iso,
            until_iso=until_iso,
            limit=limit,
            offset=offset,
        )

    def list_runs_rich(
        self,
        since_iso_str: str,
        agent: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        limit: int = 50,
    ) -> list[RichRunRow]:
        """Recent-runs listing with usage joined in (raw rows)."""
        return self._runs.list_runs_rich(since_iso_str, agent, status, executor, limit)

    def list_runs_enriched(
        self,
        *,
        range_: ActivityRange = "30d",
        agent: str | None = None,
        executor: str | None = None,
        state: str | None = None,
        limit: int = 50,
    ) -> EnrichedRunsResult:
        """Recent runs with backend/model enrichment from runner snapshots.

        Resolves backend + configured_model for each run from:
          1. ``runner_snapshot`` column (preferred — captured at run time)
          2. ``runner_profile_id`` → profiles table lookup (fallback)

        Returns ``{"results": [...], "total": <int>}``.
        """
        rows = self._runs.list_runs_rich(
            since_iso(range_), agent, state, executor, limit
        )

        profile_cache: dict[str, RunnerProfile | None] = {}

        def _profile_backend_model(profile_id: str | None) -> tuple[str | None, str | None]:
            if not profile_id:
                return None, None
            if profile_id not in profile_cache:
                profile_cache[profile_id] = self._profiles.get_by_id(profile_id)
            p = profile_cache[profile_id]
            if p is None:
                return None, None
            return p.backend, p.model

        def _state_label(status_val: str) -> str:
            return {"ok": "succeeded", "error": "failed", "running": "running"}.get(
                status_val, status_val
            )

        out: list[EnrichedRunRow] = []
        for r in rows:
            started = r["created_at"]
            finished = r["finished_at"]
            duration_ms = None
            if finished:
                try:
                    duration_ms = int(
                        (
                            datetime.fromisoformat(finished).timestamp()
                            - datetime.fromisoformat(started).timestamp()
                        )
                        * 1000
                    )
                except (ValueError, TypeError):
                    pass

            # Resolve backend/model from snapshot then profile
            snap_raw = r.get("runner_snapshot")
            backend: str | None = None
            configured_model: str | None = None
            if snap_raw:
                try:
                    snap = _json.loads(snap_raw) if isinstance(snap_raw, str) else snap_raw
                    if isinstance(snap, dict):
                        backend = snap.get("backend")
                        configured_model = snap.get("model")
                except (ValueError, TypeError):
                    pass
            if backend is None and configured_model is None:
                backend, configured_model = _profile_backend_model(r.get("runner_profile_id"))

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

    # ── Runner-profile stats ──────────────────────────────────────────

    def runner_profile_stats(
        self,
        profile_id: str,
        since: str | None = None,
        until: str | None = None,
    ) -> RunnerProfileStats:
        """Aggregate stats for a single runner profile."""
        return self._profiles.stats_for_profile(profile_id, since=since, until=until)

    def list_runner_profile_stats(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> list[RunnerProfileStats]:
        """Aggregate stats for all runner profiles."""
        return list(self._profiles.stats_all_profiles(since=since, until=until))
