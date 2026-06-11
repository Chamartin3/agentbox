"""Activity rollup queries: summaries, simple aggregates, distinct listers."""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.feedback.helpers import _duration_ms_expr
from agentbox.core.data.schema import runs, usage


class ActivityAnalyticsMixin:
    """Activity rollups and simple aggregate queries."""

    engine: Engine

    def aggregate_usage(self) -> dict:
        stmt = select(
            func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            func.count().label("runs"),
        )
        with self.engine.connect() as conn:
            row = conn.execute(stmt).first()
        return dict(row._mapping) if row else {}

    def distinct_executors(self) -> list[str]:
        """Distinct reported model values across all runs, for filter UI."""
        stmt = (
            select(func.coalesce(usage.c.model, "unknown").label("reported_model"))
            .distinct()
            .order_by("reported_model")
        )
        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(stmt)]

    def distinct_agent_ids(self) -> list[str]:
        """Distinct agent_id values across all runs, for filter UI."""
        stmt = select(runs.c.agent_id).distinct().order_by(runs.c.agent_id)
        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(stmt)]

    def activity_summary(
        self,
        since_iso: str,
        agent: str | None = None,
    ) -> dict:
        """Roll up runs in a date range into the /activity endpoint shape."""
        base_filters = [runs.c.created_at >= since_iso]
        if agent:
            base_filters.append(runs.c.agent_id == agent)

        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        duration_or_zero = case((runs.c.finished_at.isnot(None), duration_ms), else_=0)
        duration_or_null = case(
            (runs.c.finished_at.isnot(None), duration_ms), else_=None
        )
        success_duration_or_null = case(
            (
                (runs.c.status == "ok") & runs.c.finished_at.isnot(None),
                duration_ms,
            ),
            else_=None,
        )

        totals_stmt = (
            select(
                func.count().label("runs"),
                func.sum(case((runs.c.status == "running", 1), else_=0)).label(
                    "running"
                ),
                func.sum(case((runs.c.status == "ok", 1), else_=0)).label("successes"),
                func.sum(
                    case(
                        (
                            runs.c.status.in_(
                                ("error", "failed", "timeout", "incomplete")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failures"),
                func.coalesce(func.sum(duration_or_zero), 0).label("total_duration_ms"),
                func.coalesce(func.avg(duration_or_null), 0).label("avg_duration_ms"),
            )
            .select_from(runs)
            .where(*base_filters)
        )

        usage_stmt = (
            select(
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
        )

        day = func.date(runs.c.created_at).label("day")
        status_cols = [
            func.sum(case((runs.c.status == s, 1), else_=0)).label(s)
            for s in ("running", "ok", "error", "failed", "timeout", "incomplete")
        ]
        series_stmt = (
            select(
                day,
                func.count().label("runs"),
                func.sum(
                    case(
                        (
                            runs.c.status.in_(
                                ("error", "failed", "timeout", "incomplete")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failures"),
                *status_cols,
            )
            .select_from(runs)
            .where(*base_filters)
            .group_by(day)
            .order_by(day)
        )

        by_action_stmt = (
            select(
                runs.c.agent_id.label("action_name"),
                func.count().label("total"),
                func.sum(
                    case(
                        (
                            runs.c.status.in_(
                                ("error", "failed", "timeout", "incomplete")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failures"),
                func.coalesce(func.avg(success_duration_or_null), 0).label(
                    "avg_duration_ms"
                ),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "total_input_tokens"
                ),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "total_output_tokens"
                ),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
            .group_by(runs.c.agent_id)
            .order_by(func.count().desc())
        )

        reported_model_col = func.coalesce(usage.c.model, "unknown").label(
            "reported_model"
        )
        by_reported_model_stmt = (
            select(
                reported_model_col,
                func.count().label("total"),
                func.sum(
                    case(
                        (
                            runs.c.status.in_(
                                ("error", "failed", "timeout", "incomplete")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failures"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "total_input_tokens"
                ),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label(
                    "total_output_tokens"
                ),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
            .group_by("reported_model")
            .order_by(func.count().desc())
        )

        with self.engine.connect() as conn:
            totals_row = conn.execute(totals_stmt).first()
            totals = dict(totals_row._mapping) if totals_row else {}
            for k in (
                "runs",
                "running",
                "successes",
                "failures",
                "total_duration_ms",
                "avg_duration_ms",
            ):
                totals[k] = int(totals.get(k) or 0)
            total_runs = totals["runs"]
            totals["failure_rate_pct"] = (
                round(100 * totals["failures"] / total_runs, 1) if total_runs else 0.0
            )

            usage_row = conn.execute(usage_stmt).first()
            for k in ("input_tokens", "output_tokens"):
                totals[k] = int((usage_row._mapping[k] if usage_row else 0) or 0)
            totals["cost_usd"] = float(
                (usage_row._mapping["cost_usd"] if usage_row else 0) or 0.0
            )

            series = [
                {
                    "date": r._mapping["day"],
                    "runs": int(r._mapping["runs"] or 0),
                    "failures": int(r._mapping["failures"] or 0),
                    "running": int(r._mapping["running"] or 0),
                    "ok": int(r._mapping["ok"] or 0),
                    "error": int(r._mapping["error"] or 0),
                    "failed": int(r._mapping["failed"] or 0),
                    "timeout": int(r._mapping["timeout"] or 0),
                    "incomplete": int(r._mapping["incomplete"] or 0),
                }
                for r in conn.execute(series_stmt)
            ]

            by_action = []
            for r in conn.execute(by_action_stmt):
                m = r._mapping
                by_action.append(
                    {
                        "action_name": m["action_name"],
                        "total": int(m["total"] or 0),
                        "failures": int(m["failures"] or 0),
                        "avg_duration_ms": int(m["avg_duration_ms"] or 0),
                        "total_input_tokens": int(m["total_input_tokens"] or 0),
                        "total_output_tokens": int(m["total_output_tokens"] or 0),
                    }
                )

            by_reported_model = []
            for r in conn.execute(by_reported_model_stmt):
                m = r._mapping
                by_reported_model.append(
                    {
                        "reported_model": m["reported_model"],
                        "total": int(m["total"] or 0),
                        "failures": int(m["failures"] or 0),
                        "total_input_tokens": int(m["total_input_tokens"] or 0),
                        "total_output_tokens": int(m["total_output_tokens"] or 0),
                    }
                )

        return {
            "totals": totals,
            "series": series,
            "by_action": by_action,
            "by_reported_model": by_reported_model,
        }
