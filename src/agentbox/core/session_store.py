"""SQLite-backed store for runs, sessions, transcripts, and usage.

Uses SQLAlchemy Core for schema + queries. We stay on Core (not the ORM)
because the data shapes are flat rows, the public API returns plain
dicts / dataclasses, and the analytics queries are conditional aggregates
that read more clearly as SQL expressions than as ORM relationships.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    case,
    cast,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine, Row

_metadata = MetaData()

sessions = Table(
    "sessions",
    _metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("workdir", String),
    Column("created_at", String, nullable=False),
    Column("last_used_at", String),
)

runs = Table(
    "runs",
    _metadata,
    Column("id", String, primary_key=True),
    Column("agent_id", String, nullable=False),
    Column("session_id", String, ForeignKey("sessions.id")),
    Column("status", String, nullable=False),
    Column("input", String, nullable=False),
    Column("output", String),
    Column("error", String),
    Column("workdir", String),
    Column("transcript_path", String),
    Column("created_at", String, nullable=False),
    Column("finished_at", String),
    Index("runs_by_agent", "agent_id", "created_at"),
    Index("runs_by_status", "status", "created_at"),
)

usage = Table(
    "usage",
    _metadata,
    Column("run_id", String, ForeignKey("runs.id"), primary_key=True),
    Column("model", String),
    Column("input_tokens", Integer, server_default="0"),
    Column("output_tokens", Integer, server_default="0"),
    Column("cache_read_tokens", Integer, server_default="0"),
    Column("cache_write_tokens", Integer, server_default="0"),
    Column("cost_usd", Float),
)

guardrail_results = Table(
    "guardrail_results",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, ForeignKey("runs.id"), nullable=False),
    Column("name", String, nullable=False),
    Column("ok", Integer, nullable=False),
    Column("message", String),
    Column("attempt", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    CheckConstraint("ok IN (0, 1)", name="guardrail_ok_bool"),
)

run_prompts = Table(
    "run_prompts",
    _metadata,
    Column("run_id", String, ForeignKey("runs.id"), primary_key=True),
    Column("fragments", String, nullable=False),
    Column("created_at", String, nullable=False),
)

prompt_versions = Table(
    "prompt_versions",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("agent_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("content", String, nullable=False),
    Column("author", String, nullable=False, server_default="system"),
    Column("changelog", String, nullable=False, server_default=""),
    Column("is_draft", Integer, nullable=False, server_default="0"),
    Column("created_at", String, nullable=False),
    Index("idx_prompt_versions_agent", "agent_id", "version", unique=True),
)


@dataclass
class RunRecord:
    id: str
    agent_id: str
    session_id: str | None
    status: str
    input: str
    output: str | None
    error: str | None
    workdir: str | None
    transcript_path: str | None
    created_at: str
    finished_at: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_run(row: Row) -> RunRecord:
    m = row._mapping
    return RunRecord(
        id=m["id"],
        agent_id=m["agent_id"],
        session_id=m["session_id"],
        status=m["status"],
        input=m["input"],
        output=m["output"],
        error=m["error"],
        workdir=m["workdir"],
        transcript_path=m["transcript_path"],
        created_at=m["created_at"],
        finished_at=m["finished_at"],
    )


# SQLite-specific: epoch-millis duration of a run when finished.
def _duration_ms_expr(c_started, c_finished):
    epoch_finished = cast(func.strftime("%s", c_finished), Integer)
    epoch_started = cast(func.strftime("%s", c_started), Integer)
    return (epoch_finished - epoch_started) * 1000


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False — FastAPI dispatches sync handlers to a
        # threadpool, so the connection may travel across threads.
        # SQLAlchemy's pool serializes writes via the connection itself.
        self.engine: Engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._init()

    def _init(self) -> None:
        _metadata.create_all(self.engine)
        self._reap_orphaned_runs()

    def _reap_orphaned_runs(self) -> None:
        """Mark any pre-existing 'running' rows as errored on startup.

        Why: the in-process executor task that owns a run dies with the
        container. If the process is killed (or `_run` crashes after the
        runner loop but before `finish_run`), the row sits as 'running'
        forever. On startup no executor task can possibly still own those
        rows, so reap them.
        """
        reason = "orphaned: agentbox process restarted before run finished"
        with self.engine.begin() as conn:
            conn.execute(
                runs.update()
                .where(runs.c.status == "running", runs.c.finished_at.is_(None))
                .values(
                    status="error",
                    error=func.coalesce(runs.c.error, "") + reason,
                    finished_at=_now(),
                )
            )

    # ----- sessions ---------------------------------------------------------

    def create_session(self, agent_id: str, mode: str, workdir: str | None) -> str:
        sid = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                sessions.insert().values(
                    id=sid,
                    agent_id=agent_id,
                    mode=mode,
                    workdir=workdir,
                    created_at=_now(),
                )
            )
        return sid

    def touch_session(self, session_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(last_used_at=_now())
            )

    def get_session(self, session_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sessions.select().where(sessions.c.id == session_id)
            ).first()
            return dict(row._mapping) if row else None

    def set_session_workdir(self, session_id: str, workdir: str) -> None:
        """Update a session's workdir. Used by the executor on first run."""
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(workdir=workdir)
            )

    # ----- runs -------------------------------------------------------------

    def create_run(
        self,
        agent_id: str,
        input_: str,
        workdir: str,
        transcript_path: str,
        session_id: str | None = None,
    ) -> str:
        rid = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                runs.insert().values(
                    id=rid,
                    agent_id=agent_id,
                    session_id=session_id,
                    status="running",
                    input=input_,
                    workdir=workdir,
                    transcript_path=transcript_path,
                    created_at=_now(),
                )
            )
        return rid

    def finish_run(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """Mark a run terminal. Idempotent on already-terminal rows.

        The executor's finally-block and the external /complete endpoint
        can both call this; whoever gets there first wins. The other's
        call becomes a no-op so we don't overwrite a real output/error
        with the wrapper's empty result.
        """
        with self.engine.begin() as conn:
            conn.execute(
                runs.update()
                .where(
                    runs.c.id == run_id,
                    runs.c.status.in_(("running",)),
                )
                .values(
                    status="ok" if ok else "error",
                    output=output,
                    error=error,
                    finished_at=_now(),
                )
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(runs.select().where(runs.c.id == run_id)).first()
            return _row_to_run(row) if row else None

    def list_runs(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[RunRecord]:
        stmt = runs.select().order_by(runs.c.created_at.desc()).limit(limit)
        if agent_id:
            stmt = stmt.where(runs.c.agent_id == agent_id)
        with self.engine.connect() as conn:
            return [_row_to_run(r) for r in conn.execute(stmt)]

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
            rows = [_row_to_run(r) for r in conn.execute(stmt)]
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

    # ----- usage / guardrails ----------------------------------------------

    def record_usage(self, run_id: str, payload: dict) -> None:
        values = dict(
            run_id=run_id,
            model=payload.get("model"),
            input_tokens=payload.get("input_tokens", 0),
            output_tokens=payload.get("output_tokens", 0),
            cache_read_tokens=payload.get("cache_read_tokens", 0),
            cache_write_tokens=payload.get("cache_write_tokens", 0),
            cost_usd=payload.get("cost_usd"),
        )
        stmt = sqlite_insert(usage).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[usage.c.run_id],
            set_=dict(
                model=stmt.excluded.model,
                input_tokens=usage.c.input_tokens + stmt.excluded.input_tokens,
                output_tokens=usage.c.output_tokens + stmt.excluded.output_tokens,
                cache_read_tokens=usage.c.cache_read_tokens
                + stmt.excluded.cache_read_tokens,
                cache_write_tokens=usage.c.cache_write_tokens
                + stmt.excluded.cache_write_tokens,
                cost_usd=func.coalesce(usage.c.cost_usd, 0)
                + func.coalesce(stmt.excluded.cost_usd, 0),
            ),
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_usage(self, run_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                usage.select().where(usage.c.run_id == run_id)
            ).first()
            return dict(row._mapping) if row else None

    def record_guardrail(
        self, run_id: str, name: str, ok: bool, message: str | None, attempt: int
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                guardrail_results.insert().values(
                    run_id=run_id,
                    name=name,
                    ok=int(ok),
                    message=message,
                    attempt=attempt,
                    created_at=_now(),
                )
            )

    # ----- run prompts ------------------------------------------------------

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None:
        stmt = sqlite_insert(run_prompts).values(
            run_id=run_id, fragments=fragments_json, created_at=_now()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[run_prompts.c.run_id],
            set_=dict(fragments=stmt.excluded.fragments),
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_run_prompt(self, run_id: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(run_prompts.c.fragments).where(
                    run_prompts.c.run_id == run_id
                )
            ).first()
            return row[0] if row else None

    def list_guardrails(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                guardrail_results.select()
                .where(guardrail_results.c.run_id == run_id)
                .order_by(guardrail_results.c.id)
            )
            return [dict(r._mapping) for r in rows]

    # ----- prompt versions --------------------------------------------------

    def list_prompt_versions(self, agent_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                prompt_versions.select()
                .where(prompt_versions.c.agent_id == agent_id)
                .order_by(prompt_versions.c.version.desc())
            )
            return [dict(r._mapping) for r in rows]

    def get_prompt_version(self, agent_id: str, version: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.version == version,
                )
            ).first()
            return dict(row._mapping) if row else None

    def get_latest_committed_prompt(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select()
                .where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 0,
                )
                .order_by(prompt_versions.c.version.desc())
                .limit(1)
            ).first()
            return dict(row._mapping) if row else None

    def get_prompt_draft(self, agent_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                prompt_versions.select()
                .where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
                .order_by(prompt_versions.c.version.desc())
                .limit(1)
            ).first()
            return dict(row._mapping) if row else None

    def _next_prompt_version(self, agent_id: str) -> int:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.coalesce(func.max(prompt_versions.c.version), 0)).where(
                    prompt_versions.c.agent_id == agent_id
                )
            ).first()
            return int(row[0]) + 1 if row else 1

    def save_prompt_draft(self, agent_id: str, content: str, author: str = "system") -> dict:
        """Save or update the draft for an agent."""
        with self.engine.begin() as conn:
            # Delete any existing draft
            conn.execute(
                prompt_versions.delete().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
            )
            # Insert new draft at next version number
            version = self._next_prompt_version(agent_id)
            conn.execute(
                prompt_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    content=content,
                    author=author,
                    changelog="",
                    is_draft=1,
                    created_at=_now(),
                )
            )
        return self.get_prompt_draft(agent_id) or {}

    def publish_prompt(
        self, agent_id: str, changelog: str = "", author: str = "system"
    ) -> dict:
        """Publish the current draft as a committed version."""
        draft = self.get_prompt_draft(agent_id)
        if not draft:
            raise ValueError(f"No draft found for agent {agent_id!r}")

        with self.engine.begin() as conn:
            # Mark draft as committed
            conn.execute(
                prompt_versions.update()
                .where(prompt_versions.c.id == draft["id"])
                .values(
                    is_draft=0,
                    changelog=changelog,
                    created_at=_now(),
                )
            )
        return self.get_prompt_version(agent_id, draft["version"]) or {}

    def rollback_prompt(
        self, agent_id: str, target_version: int, author: str = "system"
    ) -> dict:
        """Create a new version copying the content of target_version."""
        target = self.get_prompt_version(agent_id, target_version)
        if not target:
            raise ValueError(
                f"Version {target_version} not found for agent {agent_id!r}"
            )
        if target["is_draft"]:
            raise ValueError(f"Cannot rollback to a draft version ({target_version})")

        with self.engine.begin() as conn:
            # Delete any existing draft
            conn.execute(
                prompt_versions.delete().where(
                    prompt_versions.c.agent_id == agent_id,
                    prompt_versions.c.is_draft == 1,
                )
            )
            version = self._next_prompt_version(agent_id)
            conn.execute(
                prompt_versions.insert().values(
                    agent_id=agent_id,
                    version=version,
                    content=target["content"],
                    author=author,
                    changelog=f"Rollback to version {target_version}",
                    is_draft=0,
                    created_at=_now(),
                )
            )
        return self.get_latest_committed_prompt(agent_id) or {}

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

    # ----- activity analytics ----------------------------------------------

    def activity_summary(
        self,
        since_iso: str,
        agent: str | None = None,
    ) -> dict:
        """Roll up runs in a date range into the cvman /activity shape."""
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
                func.sum(case((runs.c.status == "ok", 1), else_=0)).label(
                    "successes"
                ),
                func.sum(case((runs.c.status == "error", 1), else_=0)).label(
                    "failures"
                ),
                func.coalesce(func.sum(duration_or_zero), 0).label(
                    "total_duration_ms"
                ),
                func.coalesce(func.avg(duration_or_null), 0).label(
                    "avg_duration_ms"
                ),
            )
            .select_from(runs)
            .where(*base_filters)
        )

        usage_stmt = (
            select(
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "input_tokens"
                ),
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
                round(100 * totals["failures"] / total_runs, 1)
                if total_runs
                else 0.0
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


def read_transcript(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
