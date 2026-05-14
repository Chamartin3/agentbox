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
    literal_column,
    select,
)
from sqlalchemy.engine import Engine

from agentbox.core.data.schema import agent_versions, runs, usage


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
        agent_version: int | None = None,
        q: str | None = None,
        since_iso: str | None = None,
        until_iso: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Paginated + filterable run listing with usage + duration.

        Filters compose with AND. ``executor`` matches ``usage.model``
        (reported model from telemetry). ``q`` is a case-insensitive
        LIKE match against input/output/error so a user can grep for a
        job-application id, an error fragment, or an agent_task_id
        embedded in input.

        Returns ``(rows, total)`` where each row is a dict that includes
        all ``runs`` columns plus usage fields (input_tokens,
        output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
        model) and a computed ``duration_ms``.
        """
        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)

        cols = [
            runs,
            usage.c.input_tokens,
            usage.c.output_tokens,
            usage.c.cache_read_tokens,
            usage.c.cache_write_tokens,
            usage.c.cost_usd,
            usage.c.model,
            cast(duration_ms, Integer).label("duration_ms"),
        ]

        stmt = select(*cols).select_from(
            runs.outerjoin(usage, usage.c.run_id == runs.c.id)
        )
        count_from = runs
        if executor:
            count_from = runs.outerjoin(usage, usage.c.run_id == runs.c.id)
        count_stmt = select(func.count(func.distinct(runs.c.id))).select_from(
            count_from
        )

        conds = []
        if agent_id:
            conds.append(runs.c.agent_id == agent_id)
        if status:
            conds.append(runs.c.status == status)
        if executor:
            conds.append(func.coalesce(usage.c.model, "unknown") == executor)
        if agent_version is not None:
            # Join agent_versions only when filtering — keeps the default
            # query cost the same.
            stmt = stmt.select_from(
                runs.outerjoin(usage, usage.c.run_id == runs.c.id).outerjoin(
                    agent_versions, agent_versions.c.id == runs.c.agent_version_id
                )
            )
            count_from_av = count_from.outerjoin(
                agent_versions, agent_versions.c.id == runs.c.agent_version_id
            )
            count_stmt = select(
                func.count(func.distinct(runs.c.id))
            ).select_from(count_from_av)
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
            rows = [dict(r._mapping) for r in conn.execute(stmt)]
        return rows, total

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
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        if not since_iso and not until_iso:
            since_iso = (now - timedelta(days=7)).isoformat(timespec="seconds")
            until_iso = now.isoformat(timespec="seconds")

        # Join agent_versions only when we actually need version data —
        # either a version filter, or producing the by_version aggregate
        # (always emitted; cheap LEFT JOIN).
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
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "input_tokens"
                ),
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

        # by_version — runs grouped by agent_version. Only meaningful in a
        # single-agent scope; for the global view this groups by version
        # number which is ambiguous across agents, but we emit it anyway
        # and let the UI hide it when scope is global.
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

        # by_status — uses the same base_from so version/executor filters
        # resolve correctly.
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
            bucket_expr = func.strftime(
                "%Y-%m-%dT%H:00:00Z", runs.c.created_at
            ).label("bucket")
        else:
            bucket_expr = func.date(runs.c.created_at).label("bucket")

        series_stmt = (
            select(
                bucket_expr,
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "input_tokens"
                ),
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
                func.coalesce(usage.c.model, "unknown").label("reported_model"),
                usage.c.input_tokens,
                usage.c.output_tokens,
                usage.c.cache_read_tokens,
                usage.c.cache_write_tokens.label("cache_creation_tokens"),
                usage.c.cost_usd,
                runs.c.runner_profile_id,
                runs.c.runner_snapshot,
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
