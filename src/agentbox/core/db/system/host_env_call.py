"""HostEnvCallLog model + manager — audit log of host environment capability invocations.

Maps to the ``host_env_call_log`` table.
"""
from __future__ import annotations

from typing import Optional, cast

from sqlalchemy import JSON, select as sa_select
from sqlmodel import Field, Index

from agentbox.core.data.rows import HostEnvCallLogRow
from agentbox.core.db.base.model import Entity
from agentbox.core.db.base.manager import Manager
from agentbox.core.db.base.tablename import tablename, tableargs


class HostEnvCallLog(Entity, table=True):
    """An audit record of a host environment capability call."""

    __tablename__ = tablename("host_env_call_log")

    id: str = Field(primary_key=True)
    run_id: str = Field(nullable=False)
    workspace_id: str = Field(nullable=False)
    capability: str = Field(nullable=False)
    params: Optional[dict] = Field(default=None, sa_type=JSON)
    status: str = Field(nullable=False)
    error: Optional[str] = Field(default=None)
    surface: str = Field(nullable=False, default="host_env")
    created_at: str = Field(nullable=False)

    __table_args__ = tableargs(
        Index("ix_host_env_call_log_run", "run_id"),
        Index("ix_host_env_call_log_workspace", "workspace_id"),
    )


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

    def list_calls_for_run(self, run_id: str) -> list[HostEnvCallLogRow]:
        """Return all call-log rows for a run, ordered by created_at."""
        tbl = HostEnvCallLog.__table__
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa_select(tbl)
                .where(tbl.c.run_id == run_id)
                .order_by(tbl.c.created_at)
            )
            return [cast(HostEnvCallLogRow, dict(r._mapping)) for r in rows]
