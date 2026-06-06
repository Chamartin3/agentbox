"""Runtime context for the agent_tools stdio MCP server."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from agentbox.core.data import SessionStore


@dataclass(frozen=True)
class AgentToolsContext:
    grants: frozenset[str]  # set of canonical tool names that are active
    agent_id: str
    run_id: str
    workdir: Path
    db_path: Path

    @classmethod
    def from_env(cls) -> AgentToolsContext:
        grants_raw = os.environ.get("AGENTBOX_AGENT_TOOLS_GRANTS_JSON", "[]")
        return cls(
            grants=frozenset(json.loads(grants_raw)),
            agent_id=os.environ["AGENTBOX_AGENT_TOOLS_AGENT_ID"],
            run_id=os.environ["AGENTBOX_AGENT_TOOLS_RUN_ID"],
            workdir=Path(os.environ["AGENTBOX_AGENT_TOOLS_WORKDIR"]),
            db_path=Path(os.environ["AGENTBOX_DB_PATH"]),
        )

    @cached_property
    def store(self):
        return SessionStore(self.db_path)

    def is_granted(self, tool_name: str) -> bool:
        return tool_name in self.grants

    def audit(
        self,
        tool_name: str,
        params: dict,
        outcome: str,
        error: str | None = None,
    ) -> None:
        with contextlib.suppress(Exception):
            self.store.record_host_env_call(
                run_id=self.run_id,
                workspace_id=self.agent_id,  # reuse workspace_id column for agent_id
                capability=tool_name,
                params=params,
                status=outcome,
                error=error,
                surface="agent_tools",
            )
