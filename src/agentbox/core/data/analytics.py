"""Activity analytics mixin: rollups, time-series, per-agent / per-executor splits.

Composed into ``SessionStore`` alongside ``_CoreStore`` and
``PromptVersionsMixin``. All methods read ``self.engine`` and depend on
the tables defined in ``data.schema``.
"""

from __future__ import annotations

from sqlalchemy import (
    Integer,
    case,
    cast,
    func,
    select,
)
from sqlalchemy.engine import Engine

from agentbox.core.data.records import RunRecord, row_to_run
from agentbox.core.data.schema import runs, usage


# SQLite-specific: epoch-millis duration of a run when finished.
def _duration_ms_expr(c_started, c_finished):
    epoch_finished = cast(func.strftime("%s", c_finished), Integer)
    epoch_started = cast(func.strftime("%s", c_started), Integer)
    return (epoch_finished - epoch_started) * 1000


class AnalyticsMixin:
    """Read-only analytics queries. Requires ``self.engine: Engine``."""

    engine: Engine

    def list_runs_paged(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        q: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RunRecord], int]:
        """Paginated + filterable run listing.

        Filters compose with AND. ``executor`` matches ``usage.model``
        (which the activity API exposes as "executor"). ``q`` is a
        case-insensitive LIKE match against input/output/error so a user
        can grep for a job-application id, an error fragment, or an
        agent_task_id embedded in input. Returns ``(rows, total)`` where
        ``total`` is the un-paginated count for the same filter.
        """
        stmt = select(runs).select_from(runs)
        count_stmt = select(func.count(func.distinct(runs.c.id))).select_from(runs)
        if executor:
            stmt = stmt.join(usage, usage.c.run_id == runs.c.id, isouter=True)
            count_stmt = count_stmt.join(
                usage, usage.c.run_id == runs.c.id, isouter=True
            )

        conds = []
        if agent_id:
            conds.append(runs.c.agent_id == agent_id)
        if status:
            conds.append(runs.c.status == status)
        if executor:
            conds.append(func.coalesce(usage.c.model, "unknown") == executor)
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
        if conds:
            stmt = stmt.where(*conds)
            count_stmt = count_stmt.where(*conds)

        stmt = (
            stmt.distinct()
            .order_by(runs.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        with self.engine.connect() as conn:
            total = int(conn.execute(count_stmt).scalar() or 0)
            rows = [row_to_run(r) for r in conn.execute(stmt)]
        return rows, total

    def distinct_executors(self) -> list[str]:
        """Distinct executor (model) values across all runs, for filter UI."""
        stmt = (
            select(func.coalesce(usage.c.model, "unknown").label("executor"))
            .distinct()
            .order_by("executor")
        )
        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(stmt)]

    def distinct_agent_ids(self) -> list[str]:
        """Distinct agent_id values across all runs, for filter UI."""
        stmt = select(runs.c.agent_id).distinct().order_by(runs.c.agent_id)
        with self.engine.connect() as conn:
            return [r[0] for r in conn.execute(stmt)]

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
                func.sum(case((runs.c.status == "error", 1), else_=0)).label(
                    "failures"
                ),
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
        series_stmt = (
            select(
                day,
                func.count().label("runs"),
                func.sum(case((runs.c.status == "error", 1), else_=0)).label(
                    "failures"
                ),
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
                func.sum(case((runs.c.status == "error", 1), else_=0)).label(
                    "failures"
                ),
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

        executor_col = func.coalesce(usage.c.model, "unknown").label("executor")
        by_executor_stmt = (
            select(
                executor_col,
                func.count().label("total"),
                func.sum(case((runs.c.status == "error", 1), else_=0)).label(
                    "failures"
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
            .group_by("executor")
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

            by_executor = []
            for r in conn.execute(by_executor_stmt):
                m = r._mapping
                by_executor.append(
                    {
                        "executor": m["executor"],
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
            "by_executor": by_executor,
        }

    def list_runs_rich(
        self,
        since_iso: str,
        agent: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Recent-runs listing with usage joined in."""
        stmt = (
            select(
                runs.c.id,
                runs.c.agent_id,
                runs.c.status,
                runs.c.created_at,
                runs.c.finished_at,
                runs.c.error,
                runs.c.session_id,
                func.coalesce(usage.c.model, "unknown").label("executor"),
                usage.c.input_tokens,
                usage.c.output_tokens,
                usage.c.cache_read_tokens,
                usage.c.cache_write_tokens.label("cache_creation_tokens"),
                usage.c.cost_usd,
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(runs.c.created_at >= since_iso)
            .order_by(runs.c.created_at.desc())
            .limit(limit)
        )
        if agent:
            stmt = stmt.where(runs.c.agent_id == agent)
        if status:
            stmt = stmt.where(runs.c.status == status)
        if executor:
            stmt = stmt.where(func.coalesce(usage.c.model, "unknown") == executor)

        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt)]
