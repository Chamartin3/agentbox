"""HostEnvCallLogManager — host env call audit log CRUD."""
from __future__ import annotations

from sqlalchemy import select as sa_select

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.system.host_env_call import HostEnvCallLog


class HostEnvCallLogManager(Manager[HostEnvCallLog]):
    """Manager for the ``host_env_call_log`` table."""

    model = HostEnvCallLog

    # ------------------------------------------------------------------
    # Domain-specific operations (pure DB — no business logic)
    # ------------------------------------------------------------------

    def insert_call(
        self,
        *,
        row_id: str,
        run_id: str,
        workspace_id: str,
        capability: str,
        params: dict | None,
        status: str,
        error: str | None,
        surface: str,
        created_at: str,
    ) -> str:
        """Insert a host-env call audit log row. Returns the row id."""
        tbl = HostEnvCallLog.__table__
        with self._engine.begin() as conn:
            conn.execute(
                tbl.insert().values(
                    id=row_id,
                    run_id=run_id,
                    workspace_id=workspace_id,
                    capability=capability,
                    params=params,
                    status=status,
                    error=error,
                    surface=surface,
                    created_at=created_at,
                )
            )
        return row_id

    def list_calls_for_run(self, run_id: str) -> list[dict]:
        """Return all call-log rows for a run, ordered by created_at."""
        tbl = HostEnvCallLog.__table__
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa_select(tbl)
                .where(tbl.c.run_id == run_id)
                .order_by(tbl.c.created_at)
            )
            return [dict(r._mapping) for r in rows]
