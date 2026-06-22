"""Unit tests for RunFinalizer, cleanup_run_dir, and cleanup_workdir.

Covers:
- cleanup_run_dir: removes dir, noop on None, respects AGENTBOX_KEEP_RUN_DIRS,
  tolerates already-deleted dir.
- cleanup_workdir: skips non-ephemeral, skips persistent session, removes
  ephemeral+stateless parent dir, tolerates missing dir.
- RunFinalizer.finalize: crash-recovery path (step_result=None must not leave
  run in 'running'), normal path field mapping, conversation_uri refresh,
  dispatch lifecycle, broadcaster close, cleanup delegation — all failure modes
  are swallowed.

Collaborators are injected via fixtures in ``conftest.py``: ``finalizer`` (wired
to the shared ``mock_store``), ``run_finalize`` (drives finalize with defaults +
neutralised dispatch), ``patch_dispatch``, ``make_agent``, ``make_step_result``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster
from agentbox.core.execution.orchestrate.finalizer import (
    cleanup_run_dir,
    cleanup_workdir,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# cleanup_run_dir
# ---------------------------------------------------------------------------


class TestCleanupRunDir:
    def test_removes_dir_when_keep_run_dirs_is_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cleanup_run_dir deletes the directory when AGENTBOX_KEEP_RUN_DIRS is unset."""
        # Arrange
        run_dir = tmp_path / "run-001"
        run_dir.mkdir()
        monkeypatch.delenv("AGENTBOX_KEEP_RUN_DIRS", raising=False)

        # Act
        cleanup_run_dir(run_dir)

        # Assert
        assert not run_dir.exists()

    def test_noop_when_run_dir_is_none(self) -> None:
        """cleanup_run_dir with None must return silently without touching the filesystem."""
        # Act / Assert — no exception raised
        cleanup_run_dir(None)

    def test_keeps_dir_when_keep_run_dirs_is_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cleanup_run_dir leaves the directory intact when AGENTBOX_KEEP_RUN_DIRS=1."""
        # Arrange
        run_dir = tmp_path / "run-002"
        run_dir.mkdir()
        monkeypatch.setenv("AGENTBOX_KEEP_RUN_DIRS", "1")

        # Act
        cleanup_run_dir(run_dir)

        # Assert
        assert run_dir.exists()

    def test_tolerates_already_deleted_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cleanup_run_dir must not raise when the target directory does not exist."""
        # Arrange
        run_dir = tmp_path / "run-never-created"
        monkeypatch.delenv("AGENTBOX_KEEP_RUN_DIRS", raising=False)

        # Act / Assert — no exception
        cleanup_run_dir(run_dir)


# ---------------------------------------------------------------------------
# cleanup_workdir
# ---------------------------------------------------------------------------


class TestCleanupWorkdir:
    def test_skips_non_ephemeral_workspace(
        self, tmp_path: Path, make_agent: Callable[..., MagicMock]
    ) -> None:
        """cleanup_workdir must not remove workdirs that belong to a named workspace."""
        # Arrange
        agent = make_agent(workspace="production-ws", session_mode="stateless")
        workdir = tmp_path / "work"
        workdir.mkdir()

        # Act
        cleanup_workdir(agent, workdir)

        # Assert
        assert workdir.exists()

    def test_skips_persistent_session_even_when_workspace_is_ephemeral(
        self, tmp_path: Path, make_agent: Callable[..., MagicMock]
    ) -> None:
        """cleanup_workdir must preserve workdirs with session_mode='persistent' — history must survive the run."""
        # Arrange
        agent = make_agent(workspace="<ephemeral>", session_mode="persistent")
        workdir = tmp_path / "parent" / "work"
        workdir.mkdir(parents=True)

        # Act
        cleanup_workdir(agent, workdir)

        # Assert
        assert workdir.exists()

    def test_removes_parent_dir_for_ephemeral_stateless_session(
        self, tmp_path: Path, make_agent: Callable[..., MagicMock]
    ) -> None:
        """cleanup_workdir removes workdir.parent for ephemeral, stateless sessions."""
        # Arrange
        agent = make_agent(workspace="<ephemeral>", session_mode="stateless")
        parent = tmp_path / "run-scratch"
        workdir = parent / "agent-work"
        workdir.mkdir(parents=True)

        # Act
        cleanup_workdir(agent, workdir)

        # Assert
        assert not parent.exists()

    def test_tolerates_missing_parent_dir_for_ephemeral_stateless(
        self, tmp_path: Path, make_agent: Callable[..., MagicMock]
    ) -> None:
        """cleanup_workdir must not raise when the ephemeral workdir's parent is already absent."""
        # Arrange
        agent = make_agent(workspace="<ephemeral>", session_mode="stateless")
        workdir = tmp_path / "run-already-gone" / "work"
        # Neither parent nor workdir is created

        # Act / Assert — no exception
        cleanup_workdir(agent, workdir)


# ---------------------------------------------------------------------------
# RunFinalizer.finalize — crash-recovery path
# ---------------------------------------------------------------------------


class TestRunFinalizerCrashRecovery:
    def test_none_step_result_calls_finish_run_with_ok_false(
        self, mock_store: MagicMock, run_finalize: Callable[..., None]
    ) -> None:
        """When step_result is None (step loop blew up), finish_run must be called
        with ok=False so the run row never stays in 'running'."""
        # Act
        run_finalize(run_id="run-crash-001", step_result=None)

        # Assert
        mock_store.finish_run.assert_called_once_with(
            "run-crash-001",
            ok=False,
            output=None,
            error=None,
            status=None,
            validation_status=None,
            validation_errors=None,
            schema_validated_via=None,
        )

    def test_finish_run_is_called_even_when_store_get_run_and_dispatch_fail(
        self, mock_store: MagicMock, run_finalize: Callable[..., None]
    ) -> None:
        """finalize must persist the terminal state even when dispatch paths raise — run must not stay 'running'."""
        # Arrange
        mock_store.get_run.side_effect = RuntimeError("store unavailable")

        # Act / Assert — no exception propagated
        run_finalize(run_id="run-crash-002", step_result=None)

        # Assert — finish_run was called before get_run was attempted
        mock_store.finish_run.assert_called_once()
        assert mock_store.finish_run.call_args.kwargs["ok"] is False


# ---------------------------------------------------------------------------
# RunFinalizer.finalize — normal path field mapping
# ---------------------------------------------------------------------------


class TestRunFinalizerNormalPath:
    def test_normal_path_maps_all_step_result_fields_to_finish_run(
        self,
        mock_store: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must forward every StepResult field to store.finish_run with correct kwarg names."""
        # Arrange
        step_result = make_step_result(
            final_ok=True,
            output='{"result": 42}',
            final_error=None,
            final_status="ok",
            validation_status="ok",
            validation_errors=None,
            schema_validated_via="json-schema",
        )

        # Act
        run_finalize(run_id="run-normal-001", step_result=step_result)

        # Assert
        mock_store.finish_run.assert_called_once_with(
            "run-normal-001",
            ok=True,
            output='{"result": 42}',
            error=None,
            status="ok",
            validation_status="ok",
            validation_errors=None,
            schema_validated_via="json-schema",
        )

    def test_failed_step_result_maps_ok_false_and_error_field(
        self,
        mock_store: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize forwards ok=False and the error string when the step failed."""
        # Arrange
        step_result = make_step_result(
            final_ok=False,
            final_error="rate limit exceeded",
            final_status="failed",
            output=None,
        )

        # Act
        run_finalize(run_id="run-failed-001", step_result=step_result)

        # Assert
        call_kwargs = mock_store.finish_run.call_args.kwargs
        assert call_kwargs["ok"] is False
        assert call_kwargs["error"] == "rate limit exceeded"
        assert call_kwargs["status"] == "failed"


# ---------------------------------------------------------------------------
# RunFinalizer.finalize — conversation_uri refresh
# ---------------------------------------------------------------------------


class TestRunFinalizerConversationUri:
    def test_persists_conversation_uri_when_adapter_returns_one(
        self,
        tmp_path: Path,
        mock_store: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize calls store.set_run_conversation with the URI returned by adapter.conversation_uri."""
        # Arrange
        transcript_path = tmp_path / "transcript.jsonl"
        adapter = MagicMock()
        adapter.conversation_uri.return_value = "opencode://sessions/abc123"

        # Act
        run_finalize(
            run_id="run-conv-001",
            adapter=adapter,
            transcript_path=transcript_path,
            step_result=make_step_result(),
        )

        # Assert
        adapter.conversation_uri.assert_called_once_with(
            run_id="run-conv-001", transcript_path=str(transcript_path)
        )
        mock_store.set_run_conversation.assert_called_once_with(
            "run-conv-001",
            conversation_format=None,
            conversation_uri="opencode://sessions/abc123",
        )

    def test_skips_set_run_conversation_when_adapter_uri_returns_none(
        self,
        mock_store: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must not call store.set_run_conversation when conversation_uri returns None."""
        # Arrange
        adapter = MagicMock()
        adapter.conversation_uri.return_value = None

        # Act
        run_finalize(
            run_id="run-conv-002", adapter=adapter, step_result=make_step_result()
        )

        # Assert
        mock_store.set_run_conversation.assert_not_called()

    def test_skips_conversation_uri_when_adapter_lacks_the_attribute(
        self,
        mock_store: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must not crash and must skip set_run_conversation when adapter has no conversation_uri."""
        # Arrange
        adapter = MagicMock(spec=[])  # empty spec — no conversation_uri attribute

        # Act / Assert — no exception
        run_finalize(
            run_id="run-conv-003", adapter=adapter, step_result=make_step_result()
        )

        # Assert
        mock_store.set_run_conversation.assert_not_called()

    def test_swallows_exception_from_conversation_uri(
        self,
        mock_store: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must not propagate exceptions from adapter.conversation_uri; finish_run must still be called."""
        # Arrange
        adapter = MagicMock()
        adapter.conversation_uri.side_effect = ValueError("session not found")

        # Act / Assert — no exception propagated
        run_finalize(
            run_id="run-conv-004", adapter=adapter, step_result=make_step_result()
        )

        # Assert — the rest of finalization still completed
        mock_store.finish_run.assert_called_once()


# ---------------------------------------------------------------------------
# RunFinalizer.finalize — dispatch and broadcaster lifecycle
# ---------------------------------------------------------------------------


class TestRunFinalizerDispatchAndBroadcaster:
    def test_calls_dispatch_completion_with_refreshed_run(
        self,
        mock_store: MagicMock,
        patch_dispatch: MagicMock,
        run_finalize: Callable[..., None],
        make_agent: Callable[..., MagicMock],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize calls dispatch_completion with the run dict returned by store.get_run."""
        # Arrange
        refreshed_run = {"id": "run-dispatch-001", "status": "done"}
        mock_store.get_run.return_value = refreshed_run
        agent = make_agent()

        # Act
        run_finalize(
            run_id="run-dispatch-001", agent=agent, step_result=make_step_result()
        )

        # Assert
        patch_dispatch.assert_called_once()
        call_kwargs = patch_dispatch.call_args.kwargs
        assert call_kwargs["run"] is refreshed_run
        assert call_kwargs["agent"] is agent

    def test_skips_dispatch_when_get_run_returns_none(
        self,
        mock_store: MagicMock,
        patch_dispatch: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must not call dispatch_completion when store.get_run returns None."""
        # Arrange
        mock_store.get_run.return_value = None

        # Act
        run_finalize(run_id="run-dispatch-002", step_result=make_step_result())

        # Assert
        patch_dispatch.assert_not_called()

    def test_swallows_exception_from_dispatch_completion(
        self,
        mock_store: MagicMock,
        patch_dispatch: MagicMock,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must not propagate exceptions raised by dispatch_completion."""
        # Arrange
        mock_store.get_run.return_value = {"id": "run-dispatch-003"}
        patch_dispatch.side_effect = RuntimeError("network failure")

        # Act / Assert — no exception propagated
        run_finalize(run_id="run-dispatch-003", step_result=make_step_result())

    def test_closes_broadcaster_after_finalization(
        self, run_finalize: Callable[..., None], make_step_result: Callable[..., object]
    ) -> None:
        """finalize must call broadcaster.close() to drain WebSocket subscribers."""
        # Arrange
        broadcaster = MagicMock(spec=RunBroadcaster)

        # Act
        run_finalize(
            run_id="run-bc-001",
            broadcaster=broadcaster,
            step_result=make_step_result(),
        )

        # Assert
        broadcaster.close.assert_called_once()

    def test_tolerates_exception_from_broadcaster_close(
        self, run_finalize: Callable[..., None], make_step_result: Callable[..., object]
    ) -> None:
        """finalize must not propagate exceptions raised by broadcaster.close()."""
        # Arrange
        broadcaster = MagicMock(spec=RunBroadcaster)
        broadcaster.close.side_effect = OSError("already closed")

        # Act / Assert — no exception propagated
        run_finalize(
            run_id="run-bc-002",
            broadcaster=broadcaster,
            step_result=make_step_result(),
        )


# ---------------------------------------------------------------------------
# RunFinalizer.finalize — cleanup delegation
# ---------------------------------------------------------------------------


class TestRunFinalizerCleanupDelegation:
    def test_calls_cleanup_run_dir_with_the_provided_run_dir(
        self,
        tmp_path: Path,
        run_finalize: Callable[..., None],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must pass run_dir to cleanup_run_dir so scratch files are tidied."""
        # Arrange
        run_dir = tmp_path / "run-scratch"

        with patch(
            "agentbox.core.execution.orchestrate.finalizer.cleanup_run_dir"
        ) as mock_cleanup_run:
            # Act
            run_finalize(
                run_id="run-clean-001",
                run_dir=run_dir,
                step_result=make_step_result(),
            )

        # Assert
        mock_cleanup_run.assert_called_once_with(run_dir)

    def test_calls_cleanup_workdir_with_agent_and_workdir(
        self,
        tmp_path: Path,
        run_finalize: Callable[..., None],
        make_agent: Callable[..., MagicMock],
        make_step_result: Callable[..., object],
    ) -> None:
        """finalize must pass agent and workdir to cleanup_workdir so ephemeral dirs are removed."""
        # Arrange
        agent = make_agent()
        workdir = tmp_path / "agent-work"

        with patch(
            "agentbox.core.execution.orchestrate.finalizer.cleanup_workdir"
        ) as mock_cleanup_work:
            # Act
            run_finalize(
                run_id="run-clean-002",
                agent=agent,
                workdir=workdir,
                step_result=make_step_result(),
            )

        # Assert
        mock_cleanup_work.assert_called_once_with(agent, workdir)
