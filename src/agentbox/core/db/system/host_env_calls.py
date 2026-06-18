"""Host-env call log — audit trail for host_env tool invocations."""

from __future__ import annotations

import warnings

import uuid

from sqlalchemy.engine import Engine

from agentbox.core.db.utils import now_iso
from agentbox.core.db.schema import host_env_call_log


class HostEnvCallLogMixin:
    """Audit trail for host_env capability calls during runs."""

    engine: Engine

    def record_host_env_call(
        self,
        *,
        run_id: str,
        workspace_id: str,
        capability: str,
        params: dict | None,
        status: str,
        error: str | None = None,
        surface: str = "host_env",
    ) -> str:
        warnings.warn(
            "HostEnvCallLogMixin.record_host_env_call is deprecated; use db.host_env_call_log manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        row_id = uuid.uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                host_env_call_log.insert().values(
                    id=row_id,
                    run_id=run_id,
                    workspace_id=workspace_id,
                    capability=capability,
                    params=params,
                    status=status,
                    error=error,
                    surface=surface,
                    created_at=now_iso(),
                )
            )
        return row_id

    def list_host_env_calls_for_run(self, run_id: str) -> list[dict]:
        warnings.warn(
            "HostEnvCallLogMixin.list_host_env_calls_for_run is deprecated; use db.host_env_call_log manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            rows = conn.execute(
                host_env_call_log.select()
                .where(host_env_call_log.c.run_id == run_id)
                .order_by(host_env_call_log.c.created_at)
            )
            return [dict(r._mapping) for r in rows]
