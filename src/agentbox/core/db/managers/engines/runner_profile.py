"""RunnerProfileManager — runner backend profile CRUD.

Pure-DB operations only: no validation, no policy decisions, no field
normalization. Callers (EngineService) own those concerns.

Most query methods return ``dict`` rather than ORM model instances so the
service layer can hydrate the API-facing Pydantic models directly. ORM
returns are a later, separate purification.
"""
from __future__ import annotations

import json as _json
from typing import Any

from sqlalchemy import select, update as sa_update, delete as sa_delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.engines.runner_profile import RunnerProfile
from agentbox.core.db.schema import agent_runner_profiles, runner_profiles


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
    # Row → dict conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        """Convert a SQLAlchemy Core Row to a flat dict with Python types.

        JSON columns (``params_json``, ``headers_json``, ``extra_args_json``)
        are deserialised; integer booleans (``is_enabled``,
        ``is_system_default``) are converted to Python bool.
        """
        m = row._mapping
        return {
            "id": m["id"],
            "name": m["name"],
            "description": m.get("description"),
            "backend": m["backend"],
            "provider": m.get("provider"),
            "model": m.get("model"),
            "base_url": m.get("base_url"),
            "api_key_env": m.get("api_key_env"),
            "api_token_id": m.get("api_token_id"),
            "output_mode": m.get("output_mode") or "auto",
            "params": _json.loads(m.get("params_json") or "{}"),
            "headers": _json.loads(m.get("headers_json") or "{}"),
            "extra_args": _json.loads(m.get("extra_args_json") or "[]"),
            "is_enabled": bool(m.get("is_enabled", 1)),
            "is_system_default": bool(m.get("is_system_default", 0)),
            "created_at": m["created_at"],
            "updated_at": m["updated_at"],
        }

    # ------------------------------------------------------------------
    # Pure-DB CRUD — runner_profiles
    # ------------------------------------------------------------------

    def list_all(
        self,
        backend: str | None = None,
        provider: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
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
            return [self._row_to_dict(r) for r in conn.execute(stmt)]

    def get_by_id(self, profile_id: str) -> dict[str, Any] | None:
        """Return a single profile dict, or None."""
        stmt = select(runner_profiles).where(runner_profiles.c.id == profile_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
            return self._row_to_dict(row) if row else None

    def create_one(self, **fields: Any) -> dict[str, Any]:
        """Insert a new runner profile. Returns the created row as a dict.

        All columns must be provided (caller handles id derivation and
        defaults). JSON fields should already be serialised strings;
        boolean fields should be ``int``.
        """
        with self._engine.begin() as conn:
            conn.execute(runner_profiles.insert().values(**fields))
        row = self.get_by_id(str(fields["id"]))
        if row is None:
            raise RuntimeError(f"Failed to read back created profile {fields['id']}")
        return row

    def update_one(self, profile_id: str, **values: Any) -> dict[str, Any] | None:
        """Partial-update a runner profile. Returns the updated profile dict.

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

    def create_with_default_clear(self, **fields: Any) -> dict[str, Any]:
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
        row = self.get_by_id(str(fields["id"]))
        if row is None:
            raise RuntimeError(f"Failed to read back created profile {fields['id']}")
        return row

    def update_with_default_clear(
        self, profile_id: str, **values: Any
    ) -> dict[str, Any] | None:
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

    def get_system_default(self) -> dict[str, Any] | None:
        """Return the system-default runner profile as a dict, or None.

        Looks for the single row where ``is_system_default == 1`` (no
        ``is_enabled`` filter — config resolution needs the default even if
        disabled)."""
        stmt = select(runner_profiles).where(runner_profiles.c.is_system_default == 1).limit(1)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
            return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Agent ↔ profile binding — agent_runner_profiles
    # ------------------------------------------------------------------

    def get_agent_profile(self, agent_id: str) -> dict[str, Any] | None:
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
            return self._row_to_dict(row) if row else None

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
