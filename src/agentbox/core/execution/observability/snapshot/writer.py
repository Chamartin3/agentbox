"""Persist the immutable snapshots attached to a run row.

Failures are logged and swallowed: snapshot loss degrades the run-detail
page but is never a reason to fail the run itself.
"""

from __future__ import annotations

import logging

from agentbox.core.data import McpSnapshot, RunnerSnapshot
from agentbox.core.protocols import SnapshotStore

from .mcp import build_mcp_snapshot
from .resources import resolve_host_env_grants

logger = logging.getLogger(__name__)

__all__ = ["SnapshotWriter"]


class SnapshotWriter:
    """Persist the per-run runner / MCP / resource snapshots.

    Failures are logged and swallowed: snapshot loss degrades the
    run-detail page but is never a reason to fail the run itself.
    """

    def __init__(self, store: SnapshotStore) -> None:
        self._store = store

    def save_runner(self, run_id: str, snapshot: RunnerSnapshot) -> None:
        try:
            self._store.save_run_runner_snapshot(run_id, snapshot)
        except Exception:
            logger.exception("failed to persist runner_snapshot for run %s", run_id)

    def build_mcp_snapshot(
        self,
        *,
        workspace_id: str | None,
        host_env_grants: dict | None,
    ) -> McpSnapshot | None:
        """Resolve the workspace's effective MCP server list."""
        return build_mcp_snapshot(
            self._store,
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
            self._store.save_resource_snapshots(
                run_id,
                resource_snapshot=resource_snapshot if resource_snapshot else None,
                mcp_snapshot=mcp_snapshot,
            )
        except Exception:
            logger.exception(
                "executor: failed to persist snapshots for run %s", run_id
            )

    def resolve_host_env_grants(self, workspace_id: str | None) -> dict | None:
        """Return the workspace's non-default host-env grants, or ``None``."""
        return resolve_host_env_grants(self._store, workspace_id)
