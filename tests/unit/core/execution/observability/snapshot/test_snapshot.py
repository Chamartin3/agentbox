"""Unit tests for SnapshotWriter.

Covers:
- save_runner: delegates to store, swallows exceptions
- build_mcp_snapshot: delegates to the module-level helper
- save_resource_and_mcp: delegates to store, normalises empty list, swallows exceptions
- resolve_host_env_grants: delegates to the module-level helper
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentbox.core.data import McpSnapshot, RunnerSnapshot
from agentbox.core.execution.observability.snapshot.writer import SnapshotWriter

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_RUNNER_SNAPSHOT: RunnerSnapshot = {
    "profile_id": None,
    "profile_name": None,
    "backend": "claude_code",
    "model": "claude-3-5-sonnet",
    "timeout_seconds": 60,
    "provider": None,
    "extra_args": [],
    "source": None,
    "overrides_applied": {},
    "captured_at": "2026-07-01T00:00:00",
}

_MCP_SNAPSHOT: McpSnapshot = {
    "servers": [],
    "policy": "allow",
}


# ---------------------------------------------------------------------------
# save_runner
# ---------------------------------------------------------------------------


class TestSaveRunner:
    def test_delegates_to_store(self, mock_store: MagicMock) -> None:
        """save_runner must forward the run_id and snapshot to db.runs.save_runner_snapshot."""
        writer = SnapshotWriter(mock_store)

        writer.save_runner("run-001", _RUNNER_SNAPSHOT)

        mock_store.runs.save_runner_snapshot.assert_called_once_with(
            "run-001", _RUNNER_SNAPSHOT
        )

    def test_swallows_store_exception(self, mock_store: MagicMock) -> None:
        """save_runner must not propagate store errors — snapshot loss is non-fatal."""
        mock_store.runs.save_runner_snapshot.side_effect = RuntimeError("db locked")
        writer = SnapshotWriter(mock_store)

        # Act / Assert — no exception raised
        writer.save_runner("run-002", _RUNNER_SNAPSHOT)


# ---------------------------------------------------------------------------
# build_mcp_snapshot
# ---------------------------------------------------------------------------


class TestBuildMcpSnapshot:
    def test_delegates_to_helper_with_workspace(self, mock_store: MagicMock) -> None:
        """build_mcp_snapshot passes workspace managers and grants to the helper."""
        writer = SnapshotWriter(mock_store)

        with patch(
            "agentbox.core.execution.observability.snapshot.writer.build_mcp_snapshot"
        ) as mock_helper:
            mock_helper.return_value = _MCP_SNAPSHOT
            result = writer.build_mcp_snapshot(
                workspace_id="ws-1", host_env_grants={"shell.exec": True}
            )

        mock_helper.assert_called_once_with(
            mock_store.workspace_mcp_policies,
            mock_store.workspace_mcp_overrides,
            mock_store.workspace_mcp_tool_overrides,
            workspace_id="ws-1",
            host_env_grants={"shell.exec": True},
        )
        assert result is _MCP_SNAPSHOT

    def test_returns_none_when_no_workspace(self, mock_store: MagicMock) -> None:
        """build_mcp_snapshot returns None when workspace_id is None (helper contract)."""
        writer = SnapshotWriter(mock_store)

        with patch(
            "agentbox.core.execution.observability.snapshot.writer.build_mcp_snapshot"
        ) as mock_helper:
            mock_helper.return_value = None
            result = writer.build_mcp_snapshot(
                workspace_id=None, host_env_grants=None
            )

        assert result is None


# ---------------------------------------------------------------------------
# save_resource_and_mcp
# ---------------------------------------------------------------------------


class TestSaveResourceAndMcp:
    def test_delegates_to_store(self, mock_store: MagicMock) -> None:
        """save_resource_and_mcp forwards resource and MCP snapshots to db.runs.save_resource_snapshots."""
        writer = SnapshotWriter(mock_store)

        writer.save_resource_and_mcp(
            "run-003",
            resource_snapshot=[],
            mcp_snapshot=_MCP_SNAPSHOT,
        )

        mock_store.runs.save_resource_snapshots.assert_called_once_with(
            "run-003",
            resource_snapshot=None,  # empty list → None
            mcp_snapshot=_MCP_SNAPSHOT,
        )

    def test_passes_none_resource_snapshot_unchanged(
        self, mock_store: MagicMock
    ) -> None:
        """None resource_snapshot is forwarded as None to db.runs."""
        writer = SnapshotWriter(mock_store)

        writer.save_resource_and_mcp(
            "run-004",
            resource_snapshot=None,
            mcp_snapshot=None,
        )

        call_kwargs = mock_store.runs.save_resource_snapshots.call_args.kwargs
        assert call_kwargs["resource_snapshot"] is None
        assert call_kwargs["mcp_snapshot"] is None

    def test_swallows_store_exception(self, mock_store: MagicMock) -> None:
        """save_resource_and_mcp swallows store errors — snapshot loss is non-fatal."""
        mock_store.runs.save_resource_snapshots.side_effect = OSError("disk full")
        writer = SnapshotWriter(mock_store)

        # Act / Assert — no exception raised
        writer.save_resource_and_mcp(
            "run-005",
            resource_snapshot=None,
            mcp_snapshot=None,
        )


# ---------------------------------------------------------------------------
# resolve_host_env_grants
# ---------------------------------------------------------------------------


class TestResolveHostEnvGrants:
    def test_delegates_to_helper(self, mock_store: MagicMock) -> None:
        """resolve_host_env_grants forwards workspace_host_env_grants manager and workspace_id to the helper."""
        writer = SnapshotWriter(mock_store)

        with patch(
            "agentbox.core.execution.observability.snapshot.writer.resolve_host_env_grants"
        ) as mock_helper:
            mock_helper.return_value = {"shell.exec": {"capability": "shell.exec"}}
            result = writer.resolve_host_env_grants("ws-2")

        mock_helper.assert_called_once_with(mock_store.workspace_host_env_grants, "ws-2")
        assert result == {"shell.exec": {"capability": "shell.exec"}}

    def test_returns_none_when_no_workspace(self, mock_store: MagicMock) -> None:
        """resolve_host_env_grants returns None for workspace_id=None."""
        writer = SnapshotWriter(mock_store)

        with patch(
            "agentbox.core.execution.observability.snapshot.writer.resolve_host_env_grants"
        ) as mock_helper:
            mock_helper.return_value = None
            result = writer.resolve_host_env_grants(None)

        assert result is None
