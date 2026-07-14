"""RunnerProfile entity + manager — runner backend configuration profiles.

Maps to the ``runner_profiles`` table. Each row defines a named backend
configuration (backend, model, credentials, params, etc.).

The SQLModel ``RunnerProfile`` entity is the persistence shape; the manager
returns the pydantic ``RunnerProfileView`` (``core.data.profiles.RunnerProfile``)
so the service layer can hydrate API-facing models directly.
"""
from __future__ import annotations

import json as _json
from typing import Any, Optional

from sqlalchemy import (
    ColumnElement,
    Integer,
    cast,
    delete as sa_delete,
    func,
    select,
    update as sa_update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Field, Index

from agentbox.core.data.profiles import RunnerProfile as RunnerProfileView, RunnerProfileStats
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.tablename import tableargs, tablename
from agentbox.core.db.schema import agent_runner_profiles, runner_profiles, runs, usage


class RunnerProfile(Entity, table=True):
    """A named runner profile: backend + model + parameter configuration."""

    __tablename__ = tablename("runner_profiles")

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    backend: str = Field(nullable=False)
    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    api_key_env: Optional[str] = Field(default=None)
    output_mode: str = Field(nullable=False, default="auto")
    params_json: str = Field(nullable=False, default="{}")
    headers_json: str = Field(nullable=False, default="{}")
    extra_args_json: str = Field(nullable=False, default="[]")
    is_enabled: int = Field(nullable=False, default=1)
    is_system_default: int = Field(nullable=False, default=0)
    api_token_id: Optional[str] = Field(foreign_key="api_tokens.id", default=None)
    created_at: str = Field(nullable=False)
    updated_at: str = Field(nullable=False)

    __table_args__ = tableargs(
        Index("idx_runner_profiles_backend_provider", "backend", "provider"),
        Index("idx_runner_profiles_enabled", "is_enabled"),
    )


def _duration_ms_expr(c_started: object, c_finished: object) -> object:
    """SQLAlchemy expression: elapsed milliseconds between two timestamp columns."""
    epoch_finished = cast(func.strftime("%s", c_finished), Integer)
    epoch_started = cast(func.strftime("%s", c_started), Integer)
    return (epoch_finished - epoch_started) * 1000


class RunnerProfileManager(Manager[RunnerProfile]):
    """Manager for the ``runner_profiles`` and ``agent_runner_profiles`` tables."""

    model = RunnerProfile

    # ------------------------------------------------------------------
    # Legacy ORM helpers (kept for existing callers until Phase C)
    # ------------------------------------------------------------------

    def get_default(self) -> RunnerProfile | None:
        """Return the system-default runner profile, or None."""
        stmt = (
            select(RunnerProfile)
            .where(
                getattr(RunnerProfile, "is_system_default") == 1,
                getattr(RunnerProfile, "is_enabled") == 1,
            )
            .limit(1)
        )
        return self._scalar(stmt)

    def find_by_backend(self, backend: str) -> list[RunnerProfile]:
        """Return all enabled profiles for a given backend name."""
        return self.find(backend=backend, is_enabled=1)

    # ------------------------------------------------------------------
    # Row → Pydantic model conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_model(row: Any) -> RunnerProfileView:
        """Convert a SQLAlchemy Core Row to a RunnerProfile Pydantic model.

        JSON columns (``params_json``, ``headers_json``, ``extra_args_json``)
        are deserialised; integer booleans (``is_enabled``,
        ``is_system_default``) are converted to Python bool.
        """
        m = row._mapping
        return RunnerProfileView(
            id=m["id"],
            name=m["name"],
            description=m.get("description"),
            backend=m["backend"],
            provider=m.get("provider"),
            model=m.get("model"),
            base_url=m.get("base_url"),
            api_key_env=m.get("api_key_env"),
            api_token_id=m.get("api_token_id"),
            output_mode=m.get("output_mode") or "auto",
            params=_json.loads(m.get("params_json") or "{}"),
            headers=_json.loads(m.get("headers_json") or "{}"),
            extra_args=_json.loads(m.get("extra_args_json") or "[]"),
            is_enabled=bool(m.get("is_enabled", 1)),
            is_system_default=bool(m.get("is_system_default", 0)),
            created_at=m["created_at"],
            updated_at=m["updated_at"],
        )

    # ------------------------------------------------------------------
    # Pure-DB CRUD — runner_profiles
    # ------------------------------------------------------------------

    def list_all(
        self,
        backend: str | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
    ) -> list[RunnerProfileView]:
        """Return all runner profiles (optionally filtered), ordered by creation time."""
        stmt = select(runner_profiles)
        if backend is not None:
            stmt = stmt.where(runner_profiles.c.backend == backend)
        if provider is not None:
            stmt = stmt.where(runner_profiles.c.provider == provider)
        if enabled is not None:
            stmt = stmt.where(runner_profiles.c.is_enabled == int(enabled))
        stmt = stmt.order_by(runner_profiles.c.created_at.asc())
        with self._engine.connect() as conn:
            return [self._row_to_model(r) for r in conn.execute(stmt)]

    def get_by_id(self, profile_id: str) -> RunnerProfileView | None:
        """Return a single profile model, or None."""
        stmt = select(runner_profiles).where(runner_profiles.c.id == profile_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
            return self._row_to_model(row) if row else None

    def create_one(self, **fields: Any) -> RunnerProfileView:
        """Insert a new runner profile. Returns the created profile model.

        All columns must be provided (caller handles id derivation and
        defaults). JSON fields should already be serialised strings;
        boolean fields should be ``int``.
        """
        with self._engine.begin() as conn:
            conn.execute(runner_profiles.insert().values(**fields))
        result = self.get_by_id(str(fields["id"]))
        if result is None:
            raise RuntimeError(f"Failed to read back created profile {fields['id']}")
        return result

    def update_one(self, profile_id: str, **values: Any) -> RunnerProfileView | None:
        """Partial-update a runner profile. Returns the updated profile model.

        Only the supplied columns are changed. Returns None if the
        profile does not exist.
        """
        if not values:
            return self.get_by_id(profile_id)
        with self._engine.begin() as conn:
            result = conn.execute(
                sa_update(runner_profiles)
                .where(runner_profiles.c.id == profile_id)
                .values(**values)
            )
            if result.rowcount == 0:
                return None
        return self.get_by_id(profile_id)

    def delete_one(self, profile_id: str) -> None:
        """Delete a runner profile by ID. Silent if the profile does not exist."""
        with self._engine.begin() as conn:
            conn.execute(
                sa_delete(runner_profiles).where(runner_profiles.c.id == profile_id)
            )

    # ------------------------------------------------------------------
    # Compound atomic operations (invariant: only one system_default)
    # ------------------------------------------------------------------

    def create_with_default_clear(self, **fields: Any) -> RunnerProfileView:
        """Create a profile *and* clear ``is_system_default`` on every other
        profile — all within the same transaction so the invariant holds.

        Caller must set ``is_system_default`` appropriately in *fields*.
        """
        with self._engine.begin() as conn:
            conn.execute(
                sa_update(runner_profiles)
                .where(runner_profiles.c.is_system_default == 1)
                .values(is_system_default=0)
            )
            conn.execute(runner_profiles.insert().values(**fields))
        result = self.get_by_id(str(fields["id"]))
        if result is None:
            raise RuntimeError(f"Failed to read back created profile {fields['id']}")
        return result

    def update_with_default_clear(
        self, profile_id: str, **values: Any
    ) -> RunnerProfileView | None:
        """Partial-update a profile. If ``is_system_default`` is being set to
        ``1``, atomically clear that flag on all other profiles first.

        Returns the updated profile dict, or None if not found.
        """
        clearing = values.get("is_system_default") == 1
        with self._engine.begin() as conn:
            if clearing:
                conn.execute(
                    sa_update(runner_profiles)
                    .where(runner_profiles.c.is_system_default == 1)
                    .values(is_system_default=0)
                )
            result = conn.execute(
                sa_update(runner_profiles)
                .where(runner_profiles.c.id == profile_id)
                .values(**values)
            )
            if result.rowcount == 0:
                return None
        return self.get_by_id(profile_id)

    # ------------------------------------------------------------------
    # System default
    # ------------------------------------------------------------------

    def get_system_default(self) -> RunnerProfileView | None:
        """Return the system-default runner profile model, or None.

        Looks for the single row where ``is_system_default == 1`` (no
        ``is_enabled`` filter — config resolution needs the default even if
        disabled)."""
        stmt = select(runner_profiles).where(runner_profiles.c.is_system_default == 1).limit(1)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
            return self._row_to_model(row) if row else None

    # ------------------------------------------------------------------
    # Aggregate stats — read-only cross-table queries (plan 093)
    # ------------------------------------------------------------------

    def stats_for_profile(
        self,
        profile_id: str,
        since: str | None = None,
        until: str | None = None,
    ) -> RunnerProfileStats:
        """Aggregate run statistics for a single runner profile.

        Returns a RunnerProfileStats model with keys: profile_id, runs, succeeded, failed,
        input_tokens, output_tokens, cost_usd, avg_duration_ms, last_run_at.
        """
        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        conds: list[ColumnElement[bool]] = [runs.c.runner_profile_id == profile_id]
        if since:
            conds.append(runs.c.created_at >= since)
        if until:
            conds.append(runs.c.created_at <= until)

        _fail = runs.c.status.in_(("error", "failed", "timeout", "incomplete"))
        stmt = (
            select(
                func.count().label("runs"),
                func.sum(func.cast(runs.c.status == "ok", type_=Integer)).label("succeeded"),
                func.sum(func.cast(_fail, type_=Integer)).label("failed"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
                func.avg(duration_ms).label("avg_duration_ms"),
                func.max(runs.c.created_at).label("last_run_at"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*conds)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        m = row._mapping if row else {}
        stats_dict = {
            "profile_id": profile_id,
            "runs": int(m.get("runs") or 0),
            "succeeded": int(m.get("succeeded") or 0),
            "failed": int(m.get("failed") or 0),
            "input_tokens": int(m.get("input_tokens") or 0),
            "output_tokens": int(m.get("output_tokens") or 0),
            "cost_usd": float(m.get("cost_usd") or 0.0) or None,
            "avg_duration_ms": float(m.get("avg_duration_ms") or 0.0) if m.get("avg_duration_ms") else None,
            "last_run_at": m.get("last_run_at"),
        }
        return RunnerProfileStats.model_validate(stats_dict)

    def stats_all_profiles(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> list[RunnerProfileStats]:
        """Aggregate run statistics for every runner profile that has runs.

        Returns a list of RunnerProfileStats models; profiles without any runs are excluded.
        """
        duration_ms = _duration_ms_expr(runs.c.created_at, runs.c.finished_at)
        conds: list[ColumnElement[bool]] = [runs.c.runner_profile_id.isnot(None)]
        if since:
            conds.append(runs.c.created_at >= since)
        if until:
            conds.append(runs.c.created_at <= until)

        _fail = runs.c.status.in_(("error", "failed", "timeout", "incomplete"))
        stmt = (
            select(
                runs.c.runner_profile_id.label("profile_id"),
                func.count().label("runs"),
                func.sum(func.cast(runs.c.status == "ok", type_=Integer)).label("succeeded"),
                func.sum(func.cast(_fail, type_=Integer)).label("failed"),
                func.coalesce(func.sum(usage.c.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(usage.c.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(usage.c.cost_usd), 0).label("cost_usd"),
                func.avg(duration_ms).label("avg_duration_ms"),
                func.max(runs.c.created_at).label("last_run_at"),
            )
            .select_from(runs.outerjoin(usage, usage.c.run_id == runs.c.id))
            .where(*conds)
            .group_by(runs.c.runner_profile_id)
            .order_by(runs.c.runner_profile_id)
        )
        with self._engine.connect() as conn:
            rows = list(conn.execute(stmt))
        result = []
        for row in rows:
            m = row._mapping
            stats_dict = {
                "profile_id": m.get("profile_id") or "unknown",
                "runs": int(m.get("runs") or 0),
                "succeeded": int(m.get("succeeded") or 0),
                "failed": int(m.get("failed") or 0),
                "input_tokens": int(m.get("input_tokens") or 0),
                "output_tokens": int(m.get("output_tokens") or 0),
                "cost_usd": float(m.get("cost_usd") or 0.0) or None,
                "avg_duration_ms": float(m.get("avg_duration_ms") or 0.0) if m.get("avg_duration_ms") else None,
                "last_run_at": m.get("last_run_at"),
            }
            result.append(RunnerProfileStats.model_validate(stats_dict))
        return result

    # ------------------------------------------------------------------
    # Agent ↔ profile binding — agent_runner_profiles
    # ------------------------------------------------------------------

    def get_agent_profile(self, agent_id: str) -> RunnerProfileView | None:
        """Return the runner profile bound to *agent_id*, or None.

        Joins ``agent_runner_profiles`` + ``runner_profiles`` so the
        caller gets the full profile data.
        """
        stmt = (
            select(runner_profiles)
            .select_from(
                agent_runner_profiles.join(
                    runner_profiles,
                    agent_runner_profiles.c.runner_profile_id == runner_profiles.c.id,
                )
            )
            .where(agent_runner_profiles.c.agent_id == agent_id)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
            return self._row_to_model(row) if row else None

    def set_agent_profile(
        self, agent_id: str, profile_id: str, created_at: str, updated_at: str
    ) -> None:
        """Upsert the agent → profile binding (idempotent)."""
        stmt = sqlite_insert(agent_runner_profiles).values(
            agent_id=agent_id,
            runner_profile_id=profile_id,
            created_at=created_at,
            updated_at=updated_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[agent_runner_profiles.c.agent_id],
            set_={
                "runner_profile_id": stmt.excluded.runner_profile_id,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def clear_agent_profile(self, agent_id: str) -> None:
        """Remove the agent → profile binding. Silent if none exists."""
        with self._engine.begin() as conn:
            conn.execute(
                sa_delete(agent_runner_profiles).where(
                    agent_runner_profiles.c.agent_id == agent_id
                )
            )
