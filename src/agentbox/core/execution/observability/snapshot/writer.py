"""Persist the immutable snapshots attached to a run row.

Failures are logged and swallowed: snapshot loss degrades the run-detail
page but is never a reason to fail the run itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast


from agentbox.core.data import McpSnapshot, RunnerSnapshot
from agentbox.core.db import (
    AgentHostEnvGrantManager,
    RunManager,
    WorkspaceMcpOverrideManager,
    WorkspaceMcpPolicyManager,
    WorkspaceMcpToolOverrideManager,
)

from .mcp import build_mcp_snapshot
from .resources import resolve_host_env_grants

logger = logging.getLogger(__name__)

__all__ = ["SnapshotManagers", "SnapshotWriter"]


@dataclass(frozen=True)
class SnapshotManagers:
    """Manager bundle threaded into :class:`SnapshotWriter`."""

    runs: RunManager
    agent_host_env_grants: AgentHostEnvGrantManager
    workspace_mcp_policies: WorkspaceMcpPolicyManager
    workspace_mcp_overrides: WorkspaceMcpOverrideManager
    workspace_mcp_tool_overrides: WorkspaceMcpToolOverrideManager


class SnapshotWriter:
    """Persist the per-run runner / MCP / resource snapshots.

    Failures are logged and swallowed: snapshot loss degrades the
    run-detail page but is never a reason to fail the run itself.
    """

    def __init__(self, mgrs: SnapshotManagers) -> None:
        self._mgrs = mgrs

    def save_runner(self, run_id: str, snapshot: RunnerSnapshot) -> None:
        try:
            self._mgrs.runs.save_runner_snapshot(run_id, snapshot)
        except Exception:
            logger.exception("failed to persist runner_snapshot for run %s", run_id)

    def build_mcp_snapshot(
        self,
        *,
        workspace_id: str | None,
        host_env_grants: dict[str, Any] | None,
    ) -> McpSnapshot | None:
        """Resolve the workspace's effective MCP server list."""
        return build_mcp_snapshot(
            self._mgrs.workspace_mcp_policies,
            self._mgrs.workspace_mcp_overrides,
            self._mgrs.workspace_mcp_tool_overrides,
            workspace_id=workspace_id,
            host_env_grants=host_env_grants,
        )

    def save_resource_and_mcp(
        self,
        run_id: str,
        *,
        resource_snapshot: list | None,
        mcp_snapshot: McpSnapshot | None,
    ) -> None:
        try:
            self._mgrs.runs.save_resource_snapshots(
                run_id,
                resource_snapshot=resource_snapshot if resource_snapshot else None,
                mcp_snapshot=cast(dict, mcp_snapshot) if mcp_snapshot is not None else None,
            )
        except Exception:
            logger.exception(
                "executor: failed to persist snapshots for run %s", run_id
            )

    def resolve_host_env_grants(self, agent_id: str | None) -> dict[str, Any] | None:
        """Return the AGENT's non-default host-env grants, or ``None``."""
        return resolve_host_env_grants(self._mgrs.agent_host_env_grants, agent_id)
