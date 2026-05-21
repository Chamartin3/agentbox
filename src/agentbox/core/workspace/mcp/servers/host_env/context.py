"""Runtime context for the host-env MCP server.

Parsed once at startup from env vars; shared across all tool calls.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data.store import SessionStore


@dataclass
class HostEnvContext:
    grants: dict
    run_id: str
    workspace_id: str
    workdir: Path
    db_path: Path | None

    _store: SessionStore | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_env(cls) -> HostEnvContext:
        grants_raw = os.environ.get("AGENTBOX_HOST_ENV_GRANTS_JSON", "{}")
        grants = json.loads(grants_raw)
        run_id = os.environ.get("AGENTBOX_HOST_ENV_RUN_ID", "")
        workspace_id = os.environ.get("AGENTBOX_HOST_ENV_WORKSPACE_ID", "")
        workdir = Path(os.environ.get("AGENTBOX_HOST_ENV_WORKDIR", "."))
        db_raw = os.environ.get("AGENTBOX_DB_PATH")
        db_path = Path(db_raw) if db_raw else None
        return cls(
            grants=grants,
            run_id=run_id,
            workspace_id=workspace_id,
            workdir=workdir,
            db_path=db_path,
        )

    @property
    def store(self) -> SessionStore | None:
        if self._store is not None:
            return self._store
        if self.db_path is None:
            return None
        try:
            from agentbox.core.data.store import SessionStore

            self._store = SessionStore(self.db_path)
        except Exception:
            pass
        return self._store

    def audit(
        self,
        capability: str,
        params: dict | None,
        *,
        outcome: str,
        error: str | None = None,
    ) -> None:
        s = self.store
        if s is None:
            return
        with contextlib.suppress(Exception):
            s.record_host_env_call(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                capability=capability,
                params=params,
                status=outcome,
                error=error,
            )
