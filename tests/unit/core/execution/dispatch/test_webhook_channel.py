"""Unit tests for WebhookChannel and its helpers.

Covers ``_response_signals_failure`` (pure function) and
``WebhookChannel.deliver`` (HTTP delivery with retries).

HTTP is mocked via ``respx``; no real network calls are made.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from agentbox.core.execution.dispatch.channels.types import DeliveryResult
from agentbox.core.execution.dispatch.channels.webhook import (
    WebhookChannel,
    _response_signals_failure,
)
from agentbox.core.execution.dispatch.policy import DispatchPolicy
from agentbox.core.db import LogEvent

# --------------------------------------------------------------------------- #
# Shared fixtures and constants
# --------------------------------------------------------------------------- #

_WEBHOOK_URL = "https://webhook.example.com/callback"

_PAYLOAD: dict[str, Any] = {
    "run_id": "run-1",
    "agent_id": "agent-1",
    "session_id": None,
    "status": "ok",
    "output": '{"result": 1}',
    "output_structured": {"result": 1},
    "error": None,
    "started_at": "2024-01-01T00:00:00",
    "finished_at": "2024-01-01T00:01:00",
    "duration_ms": 60000,
    "usage": None,
    "validation_status": "ok",
    "schema_validated_via": "json-schema",
}

# Single-attempt, zero-delay policy — prevents real sleep in tests.
_ONE_SHOT = DispatchPolicy(retry_delays_s=(0.0,))
# Three-attempt, zero-delay policy — tests exhaustion scenarios.
_THREE_SHOT = DispatchPolicy(retry_delays_s=(0.0, 0.0, 0.0))
# Two-attempt, zero-delay policy — tests first-failure-then-success.
_TWO_SHOT = DispatchPolicy(retry_delays_s=(0.0, 0.0))


# --------------------------------------------------------------------------- #
# _response_signals_failure
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestResponseSignalsFailure:
    """Verify the helper that detects application-level failure in a 2xx body."""

    def test_empty_body_is_not_a_failure(self) -> None:
        """An empty response body signals no failure — delivery is considered ok."""
        assert _response_signals_failure("") is False

    def test_ok_false_field_signals_failure(self) -> None:
        """A JSON body with ``ok: false`` signals that the receiver rejected the payload."""
        assert _response_signals_failure('{"ok": false}') is True

    def test_ok_true_field_is_not_a_failure(self) -> None:
        """A JSON body with ``ok: true`` does not signal failure."""
        assert _response_signals_failure('{"ok": true}') is False

    def test_status_error_signals_failure(self) -> None:
        """``status: "error"`` in the body signals a receiver-side failure."""
        assert _response_signals_failure('{"status": "error"}') is True

    def test_status_failed_signals_failure(self) -> None:
        """``status: "failed"`` signals failure (case-insensitive)."""
        assert _response_signals_failure('{"status": "failed"}') is True

    def test_status_fail_signals_failure(self) -> None:
        """``status: "fail"`` (short form) also signals failure."""
        assert _response_signals_failure('{"status": "fail"}') is True

    def test_status_error_is_case_insensitive(self) -> None:
        """Status check is lowercased, so ``ERROR`` and ``Error`` also match."""
        assert _response_signals_failure('{"status": "ERROR"}') is True
        assert _response_signals_failure('{"status": "Failed"}') is True

    def test_status_success_is_not_a_failure(self) -> None:
        """An unrecognised positive status value does not signal failure."""
        assert _response_signals_failure('{"status": "success"}') is False

    def test_non_json_body_is_not_a_failure(self) -> None:
        """Plain-text bodies that cannot be parsed as JSON are treated as non-failure."""
        assert _response_signals_failure("plain text response") is False

    def test_json_array_body_is_not_a_failure(self) -> None:
        """A valid JSON array (not a dict) does not signal failure."""
        assert _response_signals_failure("[1, 2, 3]") is False

    def test_json_null_body_is_not_a_failure(self) -> None:
        """A ``null`` JSON body is not a failure."""
        assert _response_signals_failure("null") is False

    def test_unrelated_json_fields_are_ignored(self) -> None:
        """A dict with neither ``ok`` nor ``status`` failure fields is not a failure."""
        assert _response_signals_failure('{"message": "all good", "code": 0}') is False


# --------------------------------------------------------------------------- #
# WebhookChannel.deliver — HTTP delivery behavior
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestWebhookChannelDeliver:
    """Verify HTTP delivery, retry logic, record persistence, and event emission."""

    # ------------------------------------------------------------------
    # Empty / missing URL
    # ------------------------------------------------------------------

    async def test_empty_url_returns_not_ok_with_zero_attempts(self) -> None:
        """An empty URL string prevents any HTTP request and returns ok=False, attempts=0."""
        # Arrange
        channel = WebhookChannel()
        config: dict[str, Any] = {"url": ""}

        # Act
        result = await channel.deliver(_PAYLOAD, config, _ONE_SHOT, run_id="run-1")

        # Assert
        assert result.ok is False
        assert result.attempts == 0
        assert result.last_error is not None

    async def test_missing_url_key_returns_not_ok(self) -> None:
        """A config dict without a ``url`` key is treated the same as an empty URL."""
        # Arrange
        channel = WebhookChannel()

        # Act
        result = await channel.deliver(_PAYLOAD, {}, _ONE_SHOT, run_id="run-1")

        # Assert
        assert result.ok is False
        assert result.attempts == 0

    # ------------------------------------------------------------------
    # Success scenarios
    # ------------------------------------------------------------------

    async def test_deliver_success_on_first_attempt(self) -> None:
        """A 200 response on the first attempt returns ok=True with attempts=1."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is True
        assert result.attempts == 1
        assert result.response_status == 200

    async def test_deliver_201_created_is_also_success(self) -> None:
        """Any 2xx status code (including 201) counts as successful delivery."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(201, text="created"))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is True
        assert result.response_status == 201

    async def test_deliver_retries_on_5xx_then_succeeds(self) -> None:
        """A 503 on the first attempt followed by 200 on the second yields ok=True, attempts=2."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(
                side_effect=[
                    httpx.Response(503, text="service unavailable"),
                    httpx.Response(200, text="ok"),
                ]
            )

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _TWO_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is True
        assert result.attempts == 2

    async def test_deliver_connection_error_retried_then_succeeds(self) -> None:
        """A ConnectError on attempt 1 followed by a 200 on attempt 2 yields ok=True."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(
                side_effect=[
                    httpx.ConnectError("connection refused"),
                    httpx.Response(200, text="ok"),
                ]
            )

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _TWO_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is True
        assert result.attempts == 2

    # ------------------------------------------------------------------
    # Exhaustion / failure scenarios
    # ------------------------------------------------------------------

    async def test_deliver_exhausts_retries_and_returns_not_ok(self) -> None:
        """All three attempts returning 500 exhausts the retry budget and returns ok=False."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(500, text="error"))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _THREE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is False
        assert result.attempts == 3
        assert result.last_error is not None

    async def test_deliver_body_signals_failure_triggers_retry(self) -> None:
        """A 200 response with ``ok: false`` in the body is treated as a failure and retried."""
        # Arrange
        channel = WebhookChannel()
        failure_body = '{"ok": false, "reason": "processing error"}'

        with respx.mock:
            # All three attempts return a body-failure signal
            respx.post(_WEBHOOK_URL).mock(
                return_value=httpx.Response(200, text=failure_body)
            )

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _THREE_SHOT, run_id="run-1"
            )

        # Assert — all attempts exhausted, delivery marked failed
        assert result.ok is False
        assert result.attempts == 3

    async def test_deliver_body_signals_failure_last_error_describes_cause(self) -> None:
        """The last_error for a body-failure case mentions the body-signals-failure cause."""
        # Arrange
        channel = WebhookChannel()
        failure_body = '{"ok": false}'

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text=failure_body))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is False
        assert result.last_error is not None
        assert "body signals failure" in result.last_error.lower()

    async def test_all_connect_errors_exhausts_retries(self) -> None:
        """Three consecutive ConnectErrors exhaust all retries and return ok=False."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(
                side_effect=httpx.ConnectError("refused")
            )

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _THREE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is False
        assert result.attempts == 3

    # ------------------------------------------------------------------
    # Delivery record persistence
    # ------------------------------------------------------------------

    async def test_successful_delivery_calls_record_webhook_delivery(self, mock_store) -> None:
        """A 200 response causes store.record_webhook_delivery to be called with the status."""
        # Arrange
        channel = WebhookChannel()
        store = mock_store

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act
            await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1", store=store
            )

        # Assert
        store.record_webhook_delivery.assert_called_once()
        call_kwargs = store.record_webhook_delivery.call_args.kwargs
        assert call_kwargs["response_status"] == 200
        assert call_kwargs["error"] is None

    async def test_failed_delivery_calls_record_webhook_delivery_with_error(self, mock_store) -> None:
        """A 500 response causes record_webhook_delivery to be called with an error string."""
        # Arrange
        channel = WebhookChannel()
        store = mock_store

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(500, text="internal error"))

            # Act
            await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1", store=store
            )

        # Assert
        store.record_webhook_delivery.assert_called_once()
        call_kwargs = store.record_webhook_delivery.call_args.kwargs
        assert call_kwargs["error"] is not None
        assert "500" in call_kwargs["error"]

    async def test_record_delivery_receives_correct_run_id(self, mock_store) -> None:
        """The run_id passed to deliver is forwarded to record_webhook_delivery."""
        # Arrange
        channel = WebhookChannel()
        store = mock_store
        run_id = "run-specific-99"

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act
            await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id=run_id, store=store
            )

        # Assert
        call_kwargs = store.record_webhook_delivery.call_args.kwargs
        assert call_kwargs["run_id"] == run_id

    async def test_connection_error_calls_record_delivery_without_status(self, mock_store) -> None:
        """A transport error that never receives an HTTP response records error with status=None."""
        # Arrange
        channel = WebhookChannel()
        store = mock_store

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(side_effect=httpx.ConnectError("refused"))

            # Act
            await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1", store=store
            )

        # Assert
        call_kwargs = store.record_webhook_delivery.call_args.kwargs
        assert call_kwargs.get("response_status") is None
        assert call_kwargs["error"] is not None

    # ------------------------------------------------------------------
    # Broadcaster / event emission
    # ------------------------------------------------------------------

    async def test_deliver_emits_log_events_to_broadcaster(self, mock_broadcaster) -> None:
        """A successful delivery publishes at least two LogEvents to the broadcaster."""
        # Arrange
        channel = WebhookChannel()
        broadcaster = mock_broadcaster

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act
            await channel.deliver(
                _PAYLOAD,
                {"url": _WEBHOOK_URL},
                _ONE_SHOT,
                run_id="run-1",
                broadcaster=broadcaster,
            )

        # Assert — at minimum "scheduled" + "delivered" events
        assert broadcaster.publish.call_count >= 2
        emitted_types = [type(call.args[0]) for call in broadcaster.publish.call_args_list]
        assert all(t is LogEvent for t in emitted_types)

    async def test_deliver_emits_warn_event_on_failure(self, mock_broadcaster) -> None:
        """Each failed attempt emits a WARN-level log event to the broadcaster."""
        # Arrange
        channel = WebhookChannel()
        broadcaster = mock_broadcaster

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(500, text="err"))

            # Act
            await channel.deliver(
                _PAYLOAD,
                {"url": _WEBHOOK_URL},
                _ONE_SHOT,
                run_id="run-1",
                broadcaster=broadcaster,
            )

        # Assert — at minimum "scheduled" + "attempt failed" + "failed after N" events
        assert broadcaster.publish.call_count >= 3

    async def test_deliver_emits_events_even_on_empty_url(self, mock_broadcaster) -> None:
        """When the URL is empty no events are emitted — the early return skips _emit."""
        # Arrange
        channel = WebhookChannel()
        broadcaster = mock_broadcaster

        # Act
        await channel.deliver(
            _PAYLOAD, {"url": ""}, _ONE_SHOT, run_id="run-1", broadcaster=broadcaster
        )

        # Assert — returns before any _emit call
        broadcaster.publish.assert_not_called()

    # ------------------------------------------------------------------
    # None tolerance
    # ------------------------------------------------------------------

    async def test_deliver_tolerates_none_store(self) -> None:
        """When store=None no exception is raised and delivery still succeeds on 200."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act — store=None is the default; must not raise
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1", store=None
            )

        # Assert
        assert result.ok is True

    async def test_deliver_tolerates_none_broadcaster(self) -> None:
        """When broadcaster=None no exception is raised and delivery still succeeds on 200."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act — broadcaster=None is the default; must not raise
            result = await channel.deliver(
                _PAYLOAD,
                {"url": _WEBHOOK_URL},
                _ONE_SHOT,
                run_id="run-1",
                broadcaster=None,
            )

        # Assert
        assert result.ok is True

    async def test_deliver_tolerates_both_store_and_broadcaster_none(self) -> None:
        """Minimal call with neither store nor broadcaster must not raise."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200, text="ok"))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is True
        assert isinstance(result, DeliveryResult)

    # ------------------------------------------------------------------
    # DeliveryResult shape
    # ------------------------------------------------------------------

    async def test_successful_result_carries_response_status(self) -> None:
        """The DeliveryResult on success exposes the HTTP status code."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(202, text="accepted"))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.response_status == 202
        assert result.ok is True

    async def test_failed_result_carries_last_error(self) -> None:
        """The DeliveryResult on failure carries the last_error describing what went wrong."""
        # Arrange
        channel = WebhookChannel()

        with respx.mock:
            respx.post(_WEBHOOK_URL).mock(return_value=httpx.Response(503, text="overloaded"))

            # Act
            result = await channel.deliver(
                _PAYLOAD, {"url": _WEBHOOK_URL}, _ONE_SHOT, run_id="run-1"
            )

        # Assert
        assert result.ok is False
        assert result.last_error is not None
        assert len(result.last_error) > 0
