"""Paged and rich run listing queries."""

from __future__ import annotations

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.engine import Engine

from agentbox.core.data.execution.analytics.helpers import _duration_ms_expr
from agentbox.core.data.schema import agent_versions, runs, usage


class ListingAnalyticsMixin:
    """Paged + filtered run listing queries."""

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
            stmt = stmt.select_from(
                runs.outerjoin(usage, usage.c.run_id == runs.c.id).outerjoin(
                    agent_versions, agent_versions.c.id == runs.c.agent_version_id
                )
            )
            count_from_av = count_from.outerjoin(
                agent_versions, agent_versions.c.id == runs.c.agent_version_id
            )
            count_stmt = select(func.count(func.distinct(runs.c.id))).select_from(
                count_from_av
            )
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
