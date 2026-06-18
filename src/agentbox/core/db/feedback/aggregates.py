"""Aggregate stats query: stats_for_filters with breakdowns."""

from __future__ import annotations
import warnings

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.engine import Engine

from agentbox.core.db.feedback.helpers import _duration_ms_expr
from agentbox.core.db.schema import agent_versions, runs, usage


class AggregateAnalyticsMixin:
    """Aggregate stats with per-agent, per-model, per-status breakdowns."""

    engine: Engine

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
    ) -> dict:
        """Aggregate stats matching the same filter set as
        ``list_runs_paged``. Returns totals, top agents, top models,
        status breakdown, and a timeseries.

        Bucket size is auto-picked: hourly for spans ≤ 2 days, daily
        otherwise. Default range is last 7 days when neither
        ``since_iso`` nor ``until_iso`` is given.
        """
        warnings.warn(
            "AggregateAnalyticsMixin.stats_for_filters is deprecated; use db.runs (stats) manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        now = datetime.now(UTC)
        if not since_iso and not until_iso:
            since_iso = (now - timedelta(days=7)).isoformat(timespec="seconds")
            until_iso = now.isoformat(timespec="seconds")

        base_from = runs.outerjoin(usage, usage.c.run_id == runs.c.id).outerjoin(
            agent_versions, agent_versions.c.id == runs.c.agent_version_id
        )
        conds: list = []
        if agent_id:
            conds.append(runs.c.agent_id == agent_id)
        if status:
            conds.append(runs.c.status == status)
        if executor:
            conds.append(func.coalesce(usage.c.model, "unknown") == executor)
        if agent_version is not None:
            conds.append(agent_versions.c.version == agent_version)
        if since_iso:
            conds.append(runs.c.created_at >= since_iso)
        if until_iso:
            conds.append(runs.c.created_at <= until_iso)
        if q:
            pat = f"%{q}%"
            conds.append(
                runs.c.input.like(pat)
                | runs.c.output.like(pat)
                | runs.c.error.like(pat)
                | runs.c.id.like(pat)
            )

        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        duration_or_null = case(
            (runs.c.finished_at.isnot(None), duration_ms), else_=None
        )

        # totals
        totals_stmt = (
            select(
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
                func.coalesce(func.avg(duration_or_null), 0).label("avg_duration_ms"),
            )
            .select_from(base_from)
            .where(*conds)
        )

        # by_agent
        by_agent_stmt = (
            select(
                runs.c.agent_id,
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            )
            .select_from(base_from)
            .where(*conds)
            .group_by(runs.c.agent_id)
            .order_by(func.count().desc())
            .limit(8)
        )

        # by_model
        model_col = func.coalesce(usage.c.model, "unknown").label("model")
        by_model_stmt = (
            select(
                model_col,
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            )
            .select_from(base_from)
            .where(*conds)
            .group_by("model")
            .order_by(func.count().desc())
        )

        # by_version
        by_version_stmt = (
            select(
                agent_versions.c.version.label("version"),
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("tokens"),
            )
            .select_from(base_from)
            .where(*conds, agent_versions.c.version.isnot(None))
            .group_by(agent_versions.c.version)
            .order_by(agent_versions.c.version)
        )

        # by_status
        by_status_stmt = (
            select(
                runs.c.status,
                func.count(func.distinct(runs.c.id)).label("runs"),
            )
            .select_from(base_from)
            .where(*conds)
            .group_by(runs.c.status)
            .order_by(func.count(func.distinct(runs.c.id)).desc())
        )

        # timeseries — auto pick bucket
        if since_iso and until_iso:
            try:
                span = (
                    datetime.fromisoformat(until_iso)
                    - datetime.fromisoformat(since_iso)
                ).total_seconds()
            except Exception:
                span = 7 * 86400
        else:
            span = 7 * 86400

        if span <= 2 * 86400:
            bucket_expr = func.strftime("%Y-%m-%dT%H:00:00Z", runs.c.created_at).label(
                "bucket"
            )
        else:
            bucket_expr = func.date(runs.c.created_at).label("bucket")

        series_stmt = (
            select(
                bucket_expr,
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            )
            .select_from(base_from)
            .where(*conds)
            .group_by(literal_column("bucket"))
            .order_by(literal_column("bucket"))
        )

        with self.engine.connect() as conn:
            totals_row = conn.execute(totals_stmt).first()
            totals = dict(totals_row._mapping) if totals_row else {}
            for k in ("runs", "input_tokens", "output_tokens"):
                totals[k] = int(totals.get(k) or 0)
            totals["cost_usd"] = float(totals.get("cost_usd") or 0.0)
            totals["avg_duration_ms"] = int(totals.get("avg_duration_ms") or 0)

            by_agent = [dict(r._mapping) for r in conn.execute(by_agent_stmt)]
            by_model = [dict(r._mapping) for r in conn.execute(by_model_stmt)]
            by_version = [dict(r._mapping) for r in conn.execute(by_version_stmt)]
            by_status = [dict(r._mapping) for r in conn.execute(by_status_stmt)]
            timeseries = [dict(r._mapping) for r in conn.execute(series_stmt)]

        return {
            "totals": totals,
            "by_agent": by_agent,
            "by_model": by_model,
            "by_version": by_version,
            "by_status": by_status,
            "timeseries": timeseries,
        }
