"""Unit tests for dispatch policy module.

Covers ``apply_delivery_outcome``, ``on_delivery_done``, and
``DispatchPolicy`` from ``agentbox.core.execution.dispatch.policy``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from agentbox.core.constants import RunStatus
from agentbox.core.execution.dispatch.channels.types import DeliveryResult
from agentbox.core.execution.dispatch.policy import (
    DispatchPolicy,
    apply_delivery_outcome,
    on_delivery_done,
)


# --------------------------------------------------------------------------- #
# apply_delivery_outcome
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestApplyDeliveryOutcome:
    """Verify that run status is mutated (or not) based on delivery outcome."""

    def test_delivery_ok_leaves_ok_run_unchanged(self, make_run_record, mock_store) -> None:
        """Successful delivery on a passing run must not touch its status row."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="ok")

        # Act
        apply_delivery_outcome(mock_store, "run-1", delivered=True)

        # Assert
        mock_store.set_run_status.assert_not_called()

    def test_delivery_ok_promotes_failed_run_with_no_error(self, make_run_record, mock_store) -> None:
        """A clean failure (no error string) can be promoted back to ok once delivery succeeds."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="failed", error=None)

        # Act
        apply_delivery_outcome(mock_store, "run-1", delivered=True)

        # Assert
        mock_store.set_run_status.assert_called_once_with("run-1", RunStatus.OK)

    def test_delivery_ok_leaves_failed_run_with_real_error(self, make_run_record, mock_store) -> None:
        """A delivery success does not promote a run that failed due to a real error."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="failed", error="model timed out")

        # Act
        apply_delivery_outcome(mock_store, "run-1", delivered=True)

        # Assert
        mock_store.set_run_status.assert_not_called()

    def test_delivery_failed_flips_ok_run_to_failed(self, make_run_record, mock_store) -> None:
        """A delivery failure on a passing run flips its status so operators are alerted."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="ok")

        # Act
        apply_delivery_outcome(mock_store, "run-1", delivered=False)

        # Assert
        mock_store.set_run_status.assert_called_once_with("run-1", RunStatus.FAILED)

    def test_delivery_failed_leaves_already_failed_run(self, make_run_record, mock_store) -> None:
        """A delivery failure does not call set_run_status when the run is already failed."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="failed")

        # Act
        apply_delivery_outcome(mock_store, "run-1", delivered=False)

        # Assert
        mock_store.set_run_status.assert_not_called()

    def test_delivery_outcome_handles_missing_run(self, mock_store) -> None:
        """When the run no longer exists in the store, the function returns silently."""
        # Arrange
        mock_store.get_run.return_value = None

        # Act — must not raise
        apply_delivery_outcome(mock_store, "run-gone", delivered=True)

        # Assert
        mock_store.set_run_status.assert_not_called()

    def test_delivery_outcome_handles_store_exception(self, mock_store) -> None:
        """When the store raises during get_run, the exception is swallowed silently."""
        # Arrange
        mock_store.get_run.side_effect = RuntimeError("db unavailable")

        # Act — must not raise
        apply_delivery_outcome(mock_store, "run-1", delivered=True)

        # Assert
        mock_store.set_run_status.assert_not_called()

    def test_delivery_failed_set_status_exception_is_swallowed(self, make_run_record, mock_store) -> None:
        """If set_run_status itself raises, the exception does not bubble out."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="ok")
        mock_store.set_run_status.side_effect = RuntimeError("write failed")

        # Act — must not raise
        apply_delivery_outcome(mock_store, "run-1", delivered=False)

        # Assert — the call was still attempted
        mock_store.set_run_status.assert_called_once()


# --------------------------------------------------------------------------- #
# on_delivery_done
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestOnDeliveryDone:
    """Verify the asyncio task callback correctly bridges task results to policy."""

    def test_cancelled_task_does_not_touch_store(self, mock_store, mock_task) -> None:
        """A cancelled delivery task must not trigger any status update."""
        # Arrange
        mock_task.cancelled.return_value = True

        # Act
        with patch(
            "agentbox.core.execution.dispatch.policy.apply_delivery_outcome"
        ) as mock_apply:
            on_delivery_done(mock_task, "run-1", mock_store)

        # Assert
        mock_apply.assert_not_called()

    def test_successful_delivery_result_leaves_ok_run_unchanged(
        self, make_run_record, mock_store, mock_task
    ) -> None:
        """ok=True delivery on an ok run propagates correctly — no status flip needed."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="ok")
        mock_task.cancelled.return_value = False
        mock_task.result.return_value = DeliveryResult(ok=True, attempts=1)

        # Act
        on_delivery_done(mock_task, "run-1", mock_store)

        # Assert — ok + delivered=True → no change
        mock_store.set_run_status.assert_not_called()

    def test_failed_delivery_result_flips_ok_run_to_failed(
        self, make_run_record, mock_store, mock_task
    ) -> None:
        """ok=False delivery on an ok run triggers the delivery-failure status flip."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="ok")
        mock_task.cancelled.return_value = False
        mock_task.result.return_value = DeliveryResult(ok=False, attempts=3, last_error="timeout")

        # Act
        on_delivery_done(mock_task, "run-1", mock_store)

        # Assert
        mock_store.set_run_status.assert_called_once_with("run-1", RunStatus.FAILED)

    def test_task_that_raises_is_treated_as_delivery_failure(
        self, make_run_record, mock_store, mock_task
    ) -> None:
        """When task.result() raises, the callback treats delivery as failed."""
        # Arrange
        mock_store.get_run.return_value = make_run_record(status="ok")
        mock_task.cancelled.return_value = False
        mock_task.result.side_effect = RuntimeError("channel exploded")

        # Act
        on_delivery_done(mock_task, "run-1", mock_store)

        # Assert
        mock_store.set_run_status.assert_called_once_with("run-1", RunStatus.FAILED)

    def test_cancelled_task_skips_result_access(self, mock_store, mock_task) -> None:
        """Cancelled tasks must not call task.result() — it would raise CancelledError."""
        # Arrange
        mock_task.cancelled.return_value = True

        # Act
        on_delivery_done(mock_task, "run-1", mock_store)

        # Assert — result() never accessed
        mock_task.result.assert_not_called()


# --------------------------------------------------------------------------- #
# DispatchPolicy
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestDispatchPolicy:
    """Verify the frozen configuration dataclass carries correct defaults and invariants."""

    def test_default_policy_carries_expected_retry_delays(self) -> None:
        """Default retry schedule is 1 s / 3 s / 9 s — three exponential-ish delays."""
        # Arrange / Act
        policy = DispatchPolicy()

        # Assert
        assert policy.retry_delays_s == (1.0, 3.0, 9.0)

    def test_default_policy_has_ten_second_timeout(self) -> None:
        """Default request timeout is 10 seconds."""
        # Arrange / Act
        policy = DispatchPolicy()

        # Assert
        assert policy.request_timeout_s == 10.0

    def test_policy_is_immutable_after_construction(self) -> None:
        """DispatchPolicy is a frozen dataclass; mutation raises FrozenInstanceError."""
        # Arrange
        policy = DispatchPolicy()

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            policy.retry_delays_s = (0.1,)  # type: ignore[misc]

    def test_policy_timeout_field_is_also_frozen(self) -> None:
        """Timeout field is also immutable."""
        # Arrange
        policy = DispatchPolicy()

        # Act & Assert
        with pytest.raises(FrozenInstanceError):
            policy.request_timeout_s = 999.0  # type: ignore[misc]

    def test_custom_retry_delays_are_preserved(self) -> None:
        """Caller-supplied retry delays survive construction unchanged."""
        # Arrange / Act
        policy = DispatchPolicy(retry_delays_s=(0.1, 0.5), request_timeout_s=5.0)

        # Assert
        assert policy.retry_delays_s == (0.1, 0.5)
        assert policy.request_timeout_s == 5.0

    def test_single_retry_delay_is_valid(self) -> None:
        """A policy with a single retry delay (no retries beyond first attempt) is valid."""
        # Arrange / Act
        policy = DispatchPolicy(retry_delays_s=(0.0,))

        # Assert
        assert len(policy.retry_delays_s) == 1
