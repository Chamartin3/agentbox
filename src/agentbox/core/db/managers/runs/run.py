"""RunManager — run lifecycle operations."""
from __future__ import annotations

import json as _json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    Integer,
    case,
    cast,
    func,
    literal_column,
    select,
    update as sa_update,
)

from agentbox.core.constants import RunStatus as RS
from agentbox.core.db.utils import now_iso
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.run import Run
from agentbox.core.db.schema import agent_versions, runs, usage


def _duration_ms_expr(c_started: object, c_finished: object) -> object:
    epoch_finished = cast(func.strftime("%s", c_finished), Integer)
    epoch_started = cast(func.strftime("%s", c_started), Integer)
    return (epoch_finished - epoch_started) * 1000


class RunManager(Manager[Run]):
    """Manager for the ``runs`` table with run lifecycle operations."""

    model = Run

    def finish(
        self,
        run_id: str,
        status: str,
        output: str | None = None,
        error: str | None = None,
        finished_at: str | None = None,
    ) -> Run | None:
        """Mark a run as finished with status, output, error, and finish time."""
        values: dict[str, Any] = {"status": status}
        if output is not None:
            values["output"] = output
        if error is not None:
            values["error"] = error
        if finished_at is not None:
            values["finished_at"] = finished_at

        stmt = sa_update(Run).where(getattr(Run, "id") == run_id).values(**values)
        self._query(stmt)
        return self.get(run_id)

    def finish_full(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
        validation_errors: list[str] | None = None,
        schema_validated_via: str | None = None,
    ) -> None:
        """Mark a running run finished with optional validation fields.

        Only transitions rows still in ``running`` (idempotent on terminal).
        """
        values: dict[str, Any] = {
            "status": status
            if status
            else (RS.OK.value if ok else RS.ERROR.value),
            "output": output,
            "error": error,
            "finished_at": now_iso(),
        }
        if validation_status is not None:
            values["validation_status"] = validation_status
        if validation_errors is not None:
            values["validation_errors"] = _json.dumps(validation_errors)
        if schema_validated_via is not None:
            values["schema_validated_via"] = schema_validated_via
        stmt = (
            sa_update(Run)
            .where(getattr(Run, "id") == run_id, getattr(Run, "status") == RS.RUNNING.value)
            .values(**values)
        )
        self._query(stmt)

    def set_conversation(
        self,
        run_id: str,
        conversation_format: str | None,
        conversation_uri: str | None = None,
    ) -> None:
        """Set the conversation format and optional URI columns on a run."""
        values: dict[str, Any] = {}
        if conversation_format is not None:
            values["conversation_format"] = conversation_format
        if conversation_uri is not None:
            values["conversation_uri"] = conversation_uri
        if values:
            self._query(sa_update(Run).where(getattr(Run, "id") == run_id).values(**values))

    def set_post_outcome(
        self,
        run_id: str,
        ok: bool,
        error_kind: str | None = None,
        errors: list[dict] | None = None,
    ) -> None:
        """Set post-run outcome status (and optional error payload) on a run."""
        values: dict[str, Any] = {"post_status": "ok" if ok else "fail"}
        if errors is not None:
            values["post_errors"] = _json.dumps(
                {"error_kind": error_kind, "errors": errors}
            )
        self._query(sa_update(Run).where(getattr(Run, "id") == run_id).values(**values))

    def set_status(self, run_id: str, status: str) -> None:
        """Directly set the status column on a run."""
        self._query(sa_update(Run).where(getattr(Run, "id") == run_id).values(status=status))

    def list_runs_by_agent(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[Run]:
        """Recent runs (newest first), optionally filtered by agent_id."""
        stmt = select(Run).order_by(getattr(Run, "created_at").desc()).limit(limit)
        if agent_id:
            stmt = stmt.where(getattr(Run, "agent_id") == agent_id)
        return self._list(stmt)

    # ── snapshot writes (post-run capture onto the run row) ─────────────
    def save_snapshot(
        self,
        run_id: str,
        rendered_prompt: dict,
        variables: dict,
        validation_status: str,
        validation_errors: list[str],
        composition_snapshot: dict | None = None,
    ) -> None:
        """Persist the full post-run snapshot onto the run row."""
        values: dict[str, Any] = {
            "rendered_prompt": _json.dumps(rendered_prompt),
            "variables": _json.dumps(variables),
            "validation_status": validation_status,
            "validation_errors": _json.dumps(validation_errors),
        }
        if composition_snapshot is not None:
            values["composition_snapshot"] = _json.dumps(composition_snapshot)
        self._query(sa_update(Run).where(getattr(Run, "id") == run_id).values(**values))

    def save_composition(
        self,
        run_id: str,
        composition_snapshot: dict | None,
        rendered_prompt: dict | None,
        variables: dict | None,
    ) -> None:
        """Persist only composition/prompt/variables fields (partial update)."""
        values: dict[str, Any] = {}
        if composition_snapshot is not None:
            values["composition_snapshot"] = _json.dumps(composition_snapshot)
        if rendered_prompt is not None:
            values["rendered_prompt"] = _json.dumps(rendered_prompt)
        if variables is not None:
            values["variables"] = _json.dumps(variables)
        if values:
            self._query(sa_update(Run).where(getattr(Run, "id") == run_id).values(**values))

    def save_resource_snapshots(
        self,
        run_id: str,
        *,
        resource_snapshot: list[dict] | None = None,
        mcp_snapshot: dict | None = None,
    ) -> None:
        """Persist resource snapshot and/or MCP snapshot JSON onto the run row."""
        values: dict[str, Any] = {}
        if resource_snapshot is not None:
            values["resource_snapshot"] = _json.dumps(resource_snapshot)
        if mcp_snapshot is not None:
            values["mcp_snapshot"] = _json.dumps(mcp_snapshot)
        if values:
            self._query(sa_update(Run).where(getattr(Run, "id") == run_id).values(**values))

    def save_runner_snapshot(self, run_id: str, runner_snapshot: dict) -> None:
        """Persist the runner config snapshot; append-only (writes only if null)."""
        stmt = (
            sa_update(Run)
            .where(
                getattr(Run, "id") == run_id,
                getattr(Run, "runner_snapshot").is_(None),
            )
            .values(runner_snapshot=_json.dumps(runner_snapshot))
        )
        self._query(stmt)

    def list_orphaned_unnotified(self) -> list[Run]:
        """Runs whose error mentions 'orphaned' and have no post_status yet."""
        stmt = (
            select(Run)
            .where(
                getattr(Run, "error").like("%orphaned%"),
                getattr(Run, "post_status").is_(None),
            )
            .order_by(getattr(Run, "finished_at").asc())
        )
        return self._list(stmt)

    def reap_orphans(
        self,
        reason: str = "orphaned: agentbox process restarted before run finished",
    ) -> int:
        """Mark all ``running`` rows as ``incomplete`` (startup reaper).

        Returns the number of rows affected.
        """
        stmt = (
            sa_update(Run)
            .where(
                getattr(Run, "status") == RS.RUNNING.value,
                getattr(Run, "finished_at").is_(None),  # sqlalchemy: Column.is_() not in stubs
            )
            .values(
                status=RS.INCOMPLETE.value,
                error=func.coalesce(Run.error, "").op("||")(reason),
                finished_at=now_iso(),
            )
        )
        result = self._query(stmt)
        return result.rowcount

    # ── analytics queries (run-centric; join usage / agent_versions) ────
    def distinct_agent_ids(self) -> list[str]:
        """Distinct agent_id values across all runs, for filter UI."""
        stmt = select(runs.c.agent_id).distinct().order_by(runs.c.agent_id)
        with self._engine.connect() as conn:
            return [r[0] for r in conn.execute(stmt)]

    def activity_summary(self, since_iso: str, agent: str | None = None) -> dict:
        """Roll up runs in a date range into the /activity endpoint shape."""
        base_filters = [runs.c.created_at >= since_iso]
        if agent:
            base_filters.append(runs.c.agent_id == agent)

        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        duration_or_zero = case((runs.c.finished_at.isnot(None), duration_ms), else_=0)
        duration_or_null = case((runs.c.finished_at.isnot(None), duration_ms), else_=None)
        success_duration_or_null = case(
            ((runs.c.status == "ok") & runs.c.finished_at.isnot(None), duration_ms),
            else_=None,
        )
        _fail = runs.c.status.in_(("error", "failed", "timeout", "incomplete"))

        totals_stmt = (
            select(
                func.count().label("runs"),
                func.sum(case((runs.c.status == "running", 1), else_=0)).label("running"),
                func.sum(case((runs.c.status == "ok", 1), else_=0)).label("successes"),
                func.sum(case((_fail, 1), else_=0)).label("failures"),
                func.coalesce(func.sum(duration_or_zero), 0).label("total_duration_ms"),
                func.coalesce(func.avg(duration_or_null), 0).label("avg_duration_ms"),
            )
            .select_from(runs)
            .where(*base_filters)
        )
        usage_stmt = (
            select(
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
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
            select(day, func.count().label("runs"), func.sum(case((_fail, 1), else_=0)).label("failures"), *status_cols)
            .select_from(runs)
            .where(*base_filters)
            .group_by(day)
            .order_by(day)
        )
        by_action_stmt = (
            select(
                runs.c.agent_id.label("action_name"),
                func.count().label("total"),
                func.sum(case((_fail, 1), else_=0)).label("failures"),
                func.coalesce(func.avg(success_duration_or_null), 0).label("avg_duration_ms"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("total_output_tokens"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
            .group_by(runs.c.agent_id)
            .order_by(func.count().desc())
        )
        model_col = func.coalesce(usage.c.model, "unknown").label("reported_model")
        by_model_stmt = (
            select(
                model_col,
                func.count().label("total"),
                func.sum(case((_fail, 1), else_=0)).label("failures"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("total_input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("total_output_tokens"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*base_filters)
            .group_by("reported_model")
            .order_by(func.count().desc())
        )

        with self._engine.connect() as conn:
            totals_row = conn.execute(totals_stmt).first()
            totals = dict(totals_row._mapping) if totals_row else {}
            for k in ("runs", "running", "successes", "failures", "total_duration_ms", "avg_duration_ms"):
                totals[k] = int(totals.get(k) or 0)
            total_runs = totals["runs"]
            totals["failure_rate_pct"] = round(100 * totals["failures"] / total_runs, 1) if total_runs else 0.0
            usage_row = conn.execute(usage_stmt).first()
            for k in ("input_tokens", "output_tokens"):
                totals[k] = int((usage_row._mapping[k] if usage_row else 0) or 0)
            totals["cost_usd"] = float((usage_row._mapping["cost_usd"] if usage_row else 0) or 0.0)
            series = [
                {
                    "date": r._mapping["day"], "runs": int(r._mapping["runs"] or 0),
                    "failures": int(r._mapping["failures"] or 0), "running": int(r._mapping["running"] or 0),
                    "ok": int(r._mapping["ok"] or 0), "error": int(r._mapping["error"] or 0),
                    "failed": int(r._mapping["failed"] or 0), "timeout": int(r._mapping["timeout"] or 0),
                    "incomplete": int(r._mapping["incomplete"] or 0),
                }
                for r in conn.execute(series_stmt)
            ]
            by_action = [
                {
                    "action_name": m["action_name"], "total": int(m["total"] or 0), "failures": int(m["failures"] or 0),
                    "avg_duration_ms": int(m["avg_duration_ms"] or 0),
                    "total_input_tokens": int(m["total_input_tokens"] or 0),
                    "total_output_tokens": int(m["total_output_tokens"] or 0),
                }
                for m in (r._mapping for r in conn.execute(by_action_stmt))
            ]
            by_reported_model = [
                {
                    "reported_model": m["reported_model"], "total": int(m["total"] or 0),
                    "failures": int(m["failures"] or 0),
                    "total_input_tokens": int(m["total_input_tokens"] or 0),
                    "total_output_tokens": int(m["total_output_tokens"] or 0),
                }
                for m in (r._mapping for r in conn.execute(by_model_stmt))
            ]
        return {"totals": totals, "series": series, "by_action": by_action, "by_reported_model": by_reported_model}

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
        """Aggregate stats matching the ``list_runs_paged`` filter set."""
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
            conds.append(runs.c.input.like(pat) | runs.c.output.like(pat) | runs.c.error.like(pat) | runs.c.id.like(pat))

        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        duration_or_null = case((runs.c.finished_at.isnot(None), duration_ms), else_=None)

        totals_stmt = (
            select(
                func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
                func.coalesce(func.avg(duration_or_null), 0).label("avg_duration_ms"),
            ).select_from(base_from).where(*conds)
        )
        by_agent_stmt = (
            select(
                runs.c.agent_id, func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            ).select_from(base_from).where(*conds).group_by(runs.c.agent_id).order_by(func.count().desc()).limit(8)
        )
        model_col = func.coalesce(usage.c.model, "unknown").label("model")
        by_model_stmt = (
            select(
                model_col, func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            ).select_from(base_from).where(*conds).group_by("model").order_by(func.count().desc())
        )
        by_version_stmt = (
            select(
                agent_versions.c.version.label("version"), func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("tokens"),
            ).select_from(base_from).where(*conds, agent_versions.c.version.isnot(None))
            .group_by(agent_versions.c.version).order_by(agent_versions.c.version)
        )
        by_status_stmt = (
            select(runs.c.status, func.count(func.distinct(runs.c.id)).label("runs"))
            .select_from(base_from).where(*conds).group_by(runs.c.status)
            .order_by(func.count(func.distinct(runs.c.id)).desc())
        )

        if since_iso and until_iso:
            try:
                span = (datetime.fromisoformat(until_iso) - datetime.fromisoformat(since_iso)).total_seconds()
            except Exception:
                span = 7 * 86400
        else:
            span = 7 * 86400
        if span <= 2 * 86400:
            bucket_expr = func.strftime("%Y-%m-%dT%H:00:00Z", runs.c.created_at).label("bucket")
        else:
            bucket_expr = func.date(runs.c.created_at).label("bucket")
        series_stmt = (
            select(
                bucket_expr, func.count().label("runs"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
            ).select_from(base_from).where(*conds)
            .group_by(literal_column("bucket")).order_by(literal_column("bucket"))
        )

        with self._engine.connect() as conn:
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
            "totals": totals, "by_agent": by_agent, "by_model": by_model,
            "by_version": by_version, "by_status": by_status, "timeseries": timeseries,
        }

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
        """Paginated + filterable run listing with usage + duration."""
        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        cols = [
            runs, usage.c.input_tokens, usage.c.output_tokens, usage.c.cache_read_tokens,
            usage.c.cache_write_tokens, usage.c.cost_usd, usage.c.model,
            cast(duration_ms, Integer).label("duration_ms"),
        ]
        stmt = select(*cols).select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
        count_from = runs
        if executor:
            count_from = runs.outerjoin(usage, usage.c.run_id == runs.c.id)
        count_stmt = select(func.count(func.distinct(runs.c.id))).select_from(count_from)

        conds = []
        if agent_id:
            conds.append(runs.c.agent_id == agent_id)
        if status:
            conds.append(runs.c.status == status)
        if executor:
            conds.append(func.coalesce(usage.c.model, "unknown") == executor)
        if agent_version is not None:
            stmt = stmt.select_from(
                runs.outerjoin(usage, usage.c.run_id == runs.c.id).outerjoin(
                    agent_versions, agent_versions.c.id == runs.c.agent_version_id
                )
            )
            count_from_av = count_from.outerjoin(agent_versions, agent_versions.c.id == runs.c.agent_version_id)
            count_stmt = select(func.count(func.distinct(runs.c.id))).select_from(count_from_av)
            conds.append(agent_versions.c.version == agent_version)
        if since_iso:
            conds.append(runs.c.created_at >= since_iso)
        if until_iso:
            conds.append(runs.c.created_at <= until_iso)
        if q:
            pat = f"%{q}%"
            conds.append(runs.c.input.like(pat) | runs.c.output.like(pat) | runs.c.error.like(pat) | runs.c.id.like(pat))
        if conds:
            stmt = stmt.where(*conds)
            count_stmt = count_stmt.where(*conds)
        stmt = stmt.distinct().order_by(runs.c.created_at.desc()).limit(limit).offset(offset)

        with self._engine.connect() as conn:
            total = int(conn.execute(count_stmt).scalar() or 0)
            rows = [dict(r._mapping) for r in conn.execute(stmt)]
        return rows, total

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
                runs.c.id, runs.c.agent_id, runs.c.status, runs.c.created_at, runs.c.finished_at,
                runs.c.error, runs.c.session_id,
                func.coalesce(usage.c.model, "unknown").label("reported_model"),
                usage.c.input_tokens, usage.c.output_tokens, usage.c.cache_read_tokens,
                usage.c.cache_write_tokens.label("cache_creation_tokens"), usage.c.cost_usd,
                runs.c.runner_profile_id, runs.c.runner_snapshot,
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
        with self._engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt)]
