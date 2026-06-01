"""Runtime context for environment_mcp.

Per-agent grants (a set of canonical tool names) flow in via
``AGENTBOX_ENV_MCP_GRANTS_JSON``. No workspace-level capability dict;
the per-agent grant alone gates each tool.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore


@dataclass
class EnvironmentMcpContext:
    grants: frozenset[str]
    agent_id: str
    run_id: str
    workspace_id: str
    workdir: Path
    db_path: Path | None
    _store: "SessionStore | None" = field(default=None, repr=False, compare=False)

    @classmethod
    def from_env(cls) -> "EnvironmentMcpContext":
        grants_raw = os.environ.get("AGENTBOX_ENV_MCP_GRANTS_JSON", "[]")
        db_raw = os.environ.get("AGENTBOX_DB_PATH")
        return cls(
            grants=frozenset(json.loads(grants_raw)),
            agent_id=os.environ.get("AGENTBOX_ENV_MCP_AGENT_ID", ""),
            run_id=os.environ.get("AGENTBOX_ENV_MCP_RUN_ID", ""),
            workspace_id=os.environ.get("AGENTBOX_ENV_MCP_WORKSPACE_ID", ""),
            workdir=Path(os.environ.get("AGENTBOX_ENV_MCP_WORKDIR", ".")),
            db_path=Path(db_raw) if db_raw else None,
        )

    def is_granted(self, tool_name: str) -> bool:
        return tool_name in self.grants

    @cached_property
    def store(self) -> "SessionStore | None":
        if self.db_path is None:
            return None
        try:
            from agentbox.core.data import SessionStore

            return SessionStore(self.db_path, reap_on_startup=False)
        except Exception:
            return None

    def audit(
        self,
        tool: str,
        params: dict | None,
        outcome: str,
        error: str | None = None,
    ) -> None:
        s = self.store
        if s is None:
            return
        with contextlib.suppress(Exception):
            s.record_host_env_call(
                run_id=self.run_id,
                workspace_id=self.workspace_id or self.agent_id,
                capability=tool,
                params=params,
                status=outcome,
                error=error,
                surface="environment_mcp",
            )
