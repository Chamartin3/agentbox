"""Runner profile statistics: per-profile and cross-profile aggregates."""

from __future__ import annotations

from sqlalchemy import Integer, func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.runners._models import RunnerProfileStats, _row_to_profile
from agentbox.core.data.runs.analytics._helpers import _duration_ms_expr


class RunnerStatsMixin:
    """Per-profile and cross-profile statistics queries."""

    engine: Engine

    def get_system_default_runner_profile(self):
        """Get the system-wide default runner profile."""
        from agentbox.core.data.schema import runner_profiles

        with self.engine.connect() as conn:
            row = conn.execute(
                select(runner_profiles).where(runner_profiles.c.is_system_default == 1)
            ).first()
            return _row_to_profile(row) if row else None

    def runner_profile_stats(
        self,
        profile_id: str,
        since: str | None = None,
        until: str | None = None,
    ) -> RunnerProfileStats:
        """Get aggregated statistics for a specific runner profile."""
        from agentbox.core.data.schema import runs, usage

        base_filters = [runs.c.runner_profile_id == profile_id]
        if since:
            base_filters.append(runs.c.created_at >= since)
        if until:
            base_filters.append(runs.c.created_at <= until)

        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)

        stmt = (
            select(
                func.count().label("runs"),
                func.sum(func.cast((runs.c.status == "ok"), type_=Integer)).label(
                    "succeeded"
                ),
                func.sum(
                    func.cast(
                        (
                            runs.c.status.in_(
                                ("error", "failed", "timeout", "incomplete")
                            )
                        ),
                        type_=Integer,
                    )
                ).label("failed"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
                func.avg(duration_ms).label("avg_duration_ms"),
                func.max(runs.c.created_at).label("last_run_at"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
        )

        with self.engine.connect() as conn:
            row = conn.execute(stmt).first()

        m = row._mapping if row else {}
        return RunnerProfileStats(
            profile_id=profile_id,
            runs=int(m.get("runs") or 0),
            succeeded=int(m.get("succeeded") or 0),
            failed=int(m.get("failed") or 0),
            input_tokens=int(m.get("input_tokens") or 0),
            output_tokens=int(m.get("output_tokens") or 0),
            cost_usd=float(m.get("cost_usd") or 0.0) or None,
            avg_duration_ms=float(m.get("avg_duration_ms") or 0.0)
            if m.get("avg_duration_ms")
            else None,
            last_run_at=m.get("last_run_at"),
        )

    def list_runner_profile_stats(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> list[RunnerProfileStats]:
        """Get aggregated statistics for all runner profiles."""
        from agentbox.core.data.schema import runs, usage

        base_filters = []
        if since:
            base_filters.append(runs.c.created_at >= since)
        if until:
            base_filters.append(runs.c.created_at <= until)

        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)

        stmt = (
            select(
                runs.c.runner_profile_id.label("profile_id"),
                func.count().label("runs"),
                func.sum(func.cast((runs.c.status == "ok"), type_=Integer)).label(
                    "succeeded"
                ),
                func.sum(
                    func.cast(
                        (
                            runs.c.status.in_(
                                ("error", "failed", "timeout", "incomplete")
                            )
                        ),
                        type_=Integer,
                    )
                ).label("failed"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
                func.avg(duration_ms).label("avg_duration_ms"),
                func.max(runs.c.created_at).label("last_run_at"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
            .where(runs.c.runner_profile_id.isnot(None))
            .group_by(runs.c.runner_profile_id)
            .order_by(runs.c.runner_profile_id)
        )

        with self.engine.connect() as conn:
            rows = conn.execute(stmt)

        stats = []
        for row in rows:
            m = row._mapping
            stats.append(
                RunnerProfileStats(
                    profile_id=m.get("profile_id") or "unknown",
                    runs=int(m.get("runs") or 0),
                    succeeded=int(m.get("succeeded") or 0),
                    failed=int(m.get("failed") or 0),
                    input_tokens=int(m.get("input_tokens") or 0),
                    output_tokens=int(m.get("output_tokens") or 0),
                    cost_usd=float(m.get("cost_usd") or 0.0) or None,
                    avg_duration_ms=float(m.get("avg_duration_ms") or 0.0)
                    if m.get("avg_duration_ms")
                    else None,
                    last_run_at=m.get("last_run_at"),
                )
            )

        return stats
