"""SQLite-backed store for runs, sessions, transcripts, and usage.

Uses SQLAlchemy Core for schema + queries. We stay on Core (not the ORM)
because the data shapes are flat rows, the public API returns plain
dicts / dataclasses, and the analytics queries are conditional aggregates
that read more clearly as SQL expressions than as ORM relationships.

``SessionStore`` is composed from:
- ``_CoreStore``  — connection mgmt + sessions/runs/usage/guardrails CRUD
- ``AnalyticsMixin``       — read-only rollups and time-series
- ``PromptVersionsMixin``  — draft/publish/rollback for prompt history
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from agentbox.core.data.agent_versions import AgentVersionsMixin
from agentbox.core.data.analytics import AnalyticsMixin
from agentbox.core.data.records import RunRecord, now_iso, row_to_run
from agentbox.core.data.schema import (
    guardrail_results,
    metadata,
    run_prompts,
    runs,
    sessions,
    usage,
)


class _CoreStore:
    """Connection + CRUD for sessions, runs, usage, guardrails, run_prompts."""

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
        metadata.create_all(self.engine)
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
                    finished_at=now_iso(),
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
                    created_at=now_iso(),
                )
            )
        return sid

    def touch_session(self, session_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                sessions.update()
                .where(sessions.c.id == session_id)
                .values(last_used_at=now_iso())
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
        config_digest: str | None = None,
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
                    created_at=now_iso(),
                    config_digest=config_digest,
                )
            )
        return rid

    def finish_run(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        status: str | None = None,
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
                    status=status if status else ("ok" if ok else "error"),
                    output=output,
                    error=error,
                    finished_at=now_iso(),
                )
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(runs.select().where(runs.c.id == run_id)).first()
            return row_to_run(row) if row else None

    def list_runs(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[RunRecord]:
        stmt = runs.select().order_by(runs.c.created_at.desc()).limit(limit)
        if agent_id:
            stmt = stmt.where(runs.c.agent_id == agent_id)
        with self.engine.connect() as conn:
            return [row_to_run(r) for r in conn.execute(stmt)]

    # ----- usage / guardrails ----------------------------------------------

    def record_usage(self, run_id: str, payload: dict) -> None:
        values = {
            "run_id": run_id,
            "model": payload.get("model"),
            "input_tokens": payload.get("input_tokens", 0),
            "output_tokens": payload.get("output_tokens", 0),
            "cache_read_tokens": payload.get("cache_read_tokens", 0),
            "cache_write_tokens": payload.get("cache_write_tokens", 0),
            "cost_usd": payload.get("cost_usd"),
        }
        stmt = sqlite_insert(usage).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[usage.c.run_id],
            set_={
                "model": func.coalesce(stmt.excluded.model, usage.c.model),
                "input_tokens": usage.c.input_tokens + stmt.excluded.input_tokens,
                "output_tokens": usage.c.output_tokens + stmt.excluded.output_tokens,
                "cache_read_tokens": usage.c.cache_read_tokens
                + stmt.excluded.cache_read_tokens,
                "cache_write_tokens": usage.c.cache_write_tokens
                + stmt.excluded.cache_write_tokens,
                "cost_usd": func.coalesce(usage.c.cost_usd, 0)
                + func.coalesce(stmt.excluded.cost_usd, 0),
            },
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
                    created_at=now_iso(),
                )
            )

    def list_guardrails(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                guardrail_results.select()
                .where(guardrail_results.c.run_id == run_id)
                .order_by(guardrail_results.c.id)
            )
            return [dict(r._mapping) for r in rows]

    # ----- run prompts ------------------------------------------------------

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None:
        stmt = sqlite_insert(run_prompts).values(
            run_id=run_id, fragments=fragments_json, created_at=now_iso()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[run_prompts.c.run_id],
            set_={"fragments": stmt.excluded.fragments},
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


class SessionStore(AgentVersionsMixin, AnalyticsMixin, _CoreStore):
    """Public store façade. Composes core CRUD + analytics + agent versions."""
