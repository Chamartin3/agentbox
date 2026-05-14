"""Runner profile models and mixin for profile-based runtime configuration.

Composed into ``SessionStore``. Reads ``self.engine`` and operates on
``runner_profiles`` and ``agent_runner_profiles`` tables.
"""

from __future__ import annotations

import json as _json
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Integer, func, select
from sqlalchemy.engine import Engine, Row

from agentbox.core.data.analytics import _duration_ms_expr
from agentbox.core.data.records import now_iso


class RunnerProfile(BaseModel):
    """A runtime configuration profile for agent execution."""

    id: str
    name: str
    description: str | None = None
    backend: str
    provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_token_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    extra_args: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    is_system_default: bool = False
    created_at: str
    updated_at: str


class RunnerProfileCreate(BaseModel):
    """Mutable fields for creating a new runner profile."""

    id: str | None = None
    name: str
    description: str | None = None
    backend: str
    provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_token_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    extra_args: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    is_system_default: bool = False


class RunnerProfilePatch(BaseModel):
    """Mutable fields for updating a runner profile."""

    name: str | None = None
    description: str | None = None
    backend: str | None = None
    provider: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_token_id: str | None = None
    params: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    extra_args: list[str] | None = None
    is_enabled: bool | None = None
    is_system_default: bool | None = None


class RunnerProfileStats(BaseModel):
    """Statistics for a runner profile."""

    profile_id: str
    runs: int
    succeeded: int
    failed: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    avg_duration_ms: float | None = None
    last_run_at: str | None = None


def _slugify_id(name: str) -> str:
    """Derive a URL-safe profile id from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "profile"
    return slug


def _derive_profile_id(name: str, existing_ids: set[str]) -> str:
    """Create a unique slug-style id from *name*, appending a numeric suffix on collision."""
    base = _slugify_id(name)
    if base not in existing_ids:
        return base
    for i in range(2, 1000):
        candidate = f"{base}-{i}"
        if candidate not in existing_ids:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:8]}"


def _row_to_profile(row: Row) -> RunnerProfile:
    """Convert a database row to a RunnerProfile model."""
    m = row._mapping
    return RunnerProfile(
        id=m["id"],
        name=m["name"],
        description=m.get("description"),
        backend=m["backend"],
        provider=m.get("provider"),
        model=m.get("model"),
        timeout_seconds=m.get("timeout_seconds"),
        base_url=m.get("base_url"),
        api_key_env=m.get("api_key_env"),
        api_token_id=m.get("api_token_id"),
        params=_json.loads(m.get("params_json") or "{}"),
        headers=_json.loads(m.get("headers_json") or "{}"),
        extra_args=_json.loads(m.get("extra_args_json") or "[]"),
        is_enabled=bool(m.get("is_enabled", 1)),
        is_system_default=bool(m.get("is_system_default", 0)),
        created_at=m["created_at"],
        updated_at=m["updated_at"],
    )


class RunnerProfilesMixin:
    """Runner profile CRUD and stats queries. Requires ``self.engine: Engine``."""

    engine: Engine

    def create_runner_profile(self, data: RunnerProfileCreate) -> RunnerProfile:
        """Create a new runner profile.

        If ``data.id`` is omitted, derives one from ``slugify(name)``;
        on collision appends a short numeric suffix.

        If is_system_default=True, atomically clears is_system_default on
        all other profiles in the same transaction.
        """
        from sqlalchemy import insert

        if data.id:
            profile_id = data.id
        else:
            existing = self.list_runner_profiles()
            existing_ids = {p.id for p in existing}
            profile_id = _derive_profile_id(data.name, existing_ids)
        now = now_iso()

        with self.engine.begin() as conn:
            # If setting as system default, clear other defaults
            if data.is_system_default:
                from agentbox.core.data.schema import runner_profiles

                conn.execute(
                    runner_profiles.update()
                    .where(runner_profiles.c.is_system_default == 1)
                    .values(is_system_default=0)
                )

            from agentbox.core.data.schema import runner_profiles

            conn.execute(
                insert(runner_profiles).values(
                    id=profile_id,
                    name=data.name,
                    description=data.description,
                    backend=data.backend,
                    provider=data.provider,
                    model=data.model,
                    timeout_seconds=data.timeout_seconds,
                    base_url=data.base_url,
                    api_key_env=data.api_key_env,
                    api_token_id=data.api_token_id,
                    params_json=_json.dumps(data.params),
                    headers_json=_json.dumps(data.headers),
                    extra_args_json=_json.dumps(data.extra_args),
                    is_enabled=int(data.is_enabled),
                    is_system_default=int(data.is_system_default),
                    created_at=now,
                    updated_at=now,
                )
            )

        return self.get_runner_profile(profile_id) or RunnerProfile(
            id=profile_id,
            name=data.name,
            description=data.description,
            backend=data.backend,
            provider=data.provider,
            model=data.model,
            timeout_seconds=data.timeout_seconds,
            base_url=data.base_url,
            api_key_env=data.api_key_env,
            params=data.params,
            headers=data.headers,
            extra_args=data.extra_args,
            is_enabled=data.is_enabled,
            is_system_default=data.is_system_default,
            created_at=now,
            updated_at=now,
        )

    def list_runner_profiles(
        self,
        backend: str | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
    ) -> list[RunnerProfile]:
        """List runner profiles with optional filters."""
        from agentbox.core.data.schema import runner_profiles

        stmt = select(runner_profiles)
        conds = []
        if backend is not None:
            conds.append(runner_profiles.c.backend == backend)
        if provider is not None:
            conds.append(runner_profiles.c.provider == provider)
        if enabled is not None:
            conds.append(runner_profiles.c.is_enabled == int(enabled))

        if conds:
            stmt = stmt.where(*conds)

        stmt = stmt.order_by(runner_profiles.c.created_at.asc())

        with self.engine.connect() as conn:
            return [_row_to_profile(r) for r in conn.execute(stmt)]

    def get_runner_profile(self, profile_id: str) -> RunnerProfile | None:
        """Get a runner profile by ID."""
        from agentbox.core.data.schema import runner_profiles

        with self.engine.connect() as conn:
            row = conn.execute(
                select(runner_profiles).where(runner_profiles.c.id == profile_id)
            ).first()
            return _row_to_profile(row) if row else None

    def update_runner_profile(
        self, profile_id: str, patch: RunnerProfilePatch
    ) -> RunnerProfile:
        """Update a runner profile with a partial patch.

        If is_system_default is being set True, atomically clears
        is_system_default on all other profiles.
        """
        from agentbox.core.data.schema import runner_profiles

        values: dict[str, Any] = {}
        if patch.name is not None:
            values["name"] = patch.name
        if patch.description is not None:
            values["description"] = patch.description
        if patch.backend is not None:
            values["backend"] = patch.backend
        if patch.provider is not None:
            values["provider"] = patch.provider
        if patch.model is not None:
            values["model"] = patch.model
        if patch.timeout_seconds is not None:
            values["timeout_seconds"] = patch.timeout_seconds
        if patch.base_url is not None:
            values["base_url"] = patch.base_url
        if patch.api_key_env is not None:
            values["api_key_env"] = patch.api_key_env
        if patch.api_token_id is not None:
            values["api_token_id"] = patch.api_token_id or None
        if patch.params is not None:
            values["params_json"] = _json.dumps(patch.params)
        if patch.headers is not None:
            values["headers_json"] = _json.dumps(patch.headers)
        if patch.extra_args is not None:
            values["extra_args_json"] = _json.dumps(patch.extra_args)
        if patch.is_enabled is not None:
            values["is_enabled"] = int(patch.is_enabled)
        if patch.is_system_default is not None:
            values["is_system_default"] = int(patch.is_system_default)

        if not values:
            # No changes; return current profile
            return self.get_runner_profile(profile_id) or RunnerProfile(
                id=profile_id,
                name="unknown",
                backend="unknown",
                created_at=now_iso(),
                updated_at=now_iso(),
            )

        values["updated_at"] = now_iso()

        with self.engine.begin() as conn:
            # If setting as system default, clear other defaults
            if patch.is_system_default is True:
                conn.execute(
                    runner_profiles.update()
                    .where(runner_profiles.c.is_system_default == 1)
                    .values(is_system_default=0)
                )

            conn.execute(
                runner_profiles.update()
                .where(runner_profiles.c.id == profile_id)
                .values(**values)
            )

        return self.get_runner_profile(profile_id) or RunnerProfile(
            id=profile_id,
            name="unknown",
            backend="unknown",
            created_at=now_iso(),
            updated_at=now_iso(),
        )

    def delete_runner_profile(self, profile_id: str) -> None:
        """Delete a runner profile by ID."""
        from agentbox.core.data.schema import runner_profiles

        with self.engine.begin() as conn:
            conn.execute(
                runner_profiles.delete().where(runner_profiles.c.id == profile_id)
            )

    def set_agent_runner_profile(
        self, agent_id: str, profile_id: str
    ) -> RunnerProfile:
        """Bind a runner profile to an agent."""
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        from agentbox.core.data.schema import agent_runner_profiles

        now = now_iso()
        stmt = sqlite_insert(agent_runner_profiles).values(
            agent_id=agent_id,
            runner_profile_id=profile_id,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[agent_runner_profiles.c.agent_id],
            set_={
                "runner_profile_id": stmt.excluded.runner_profile_id,
                "updated_at": stmt.excluded.updated_at,
            },
        )

        with self.engine.begin() as conn:
            conn.execute(stmt)

        return self.get_runner_profile(profile_id) or RunnerProfile(
            id=profile_id,
            name="unknown",
            backend="unknown",
            created_at=now_iso(),
            updated_at=now_iso(),
        )

    def get_agent_runner_profile(self, agent_id: str) -> RunnerProfile | None:
        """Get the runner profile bound to an agent."""
        from agentbox.core.data.schema import agent_runner_profiles, runner_profiles

        with self.engine.connect() as conn:
            row = conn.execute(
                select(runner_profiles).join(
                    agent_runner_profiles,
                    agent_runner_profiles.c.runner_profile_id == runner_profiles.c.id,
                )
                .where(agent_runner_profiles.c.agent_id == agent_id)
            ).first()
            return _row_to_profile(row) if row else None

    def clear_agent_runner_profile(self, agent_id: str) -> None:
        """Remove the runner profile binding from an agent."""
        from agentbox.core.data.schema import agent_runner_profiles

        with self.engine.begin() as conn:
            conn.execute(
                agent_runner_profiles.delete().where(
                    agent_runner_profiles.c.agent_id == agent_id
                )
            )

    def get_system_default_runner_profile(self) -> RunnerProfile | None:
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
                func.sum(
                    func.cast(
                        (runs.c.status == "ok"), type_=Integer
                    )
                ).label("succeeded"),
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
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "input_tokens"
                ),
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
                func.sum(
                    func.cast(
                        (runs.c.status == "ok"), type_=Integer
                    )
                ).label("succeeded"),
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
                func.coalesce(func.sum(usage.c.input_tokens), 0).label(
                    "input_tokens"
                ),
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
