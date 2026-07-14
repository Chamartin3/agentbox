"""Runtime context for the host-env MCP server.

Parsed once at startup from env vars; shared across all tool calls.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from agentbox.core.db.database import Database  # allowed: secondary-store opener (plan 110)
from agentbox.core.db.config import record_host_env_call


@dataclass
class HostEnvContext:
    grants: dict
    run_id: str
    workspace_id: str
    workdir: Path
    db_path: Path | None

    _db: Database | None = field(default=None, repr=False, compare=False)

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
    def db(self) -> Database | None:
        if self._db is not None:
            return self._db
        if self.db_path is None:
            return None
        try:
            self._db = Database(self.db_path)
        except Exception:
            pass
        return self._db

    def audit(
        self,
        capability: str,
        params: dict | None,
        *,
        outcome: str,
        error: str | None = None,
    ) -> None:
        with contextlib.suppress(Exception):
            record_host_env_call(
                run_id=self.run_id,
                workspace_id=self.workspace_id,
                capability=capability,
                params=params,
                status=outcome,
                error=error,
            )
