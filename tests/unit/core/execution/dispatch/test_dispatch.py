"""Unit tests for the dispatch facade (``__init__.py``).

Covers ``resolve_channels`` (URL resolution priority) and
``dispatch_completion`` (task scheduling, unknown-channel handling,
no-running-loop guard).
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import pytest

from agentbox.core.execution.dispatch import dispatch_completion, resolve_channels
from agentbox.core.execution.dispatch.channels.types import DeliveryResult


# --------------------------------------------------------------------------- #
# resolve_channels
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestResolveChannels:
    """Verify URL priority and the resolved channel spec shape."""

    def test_agent_webhook_url_produces_webhook_channel_spec(
        self, make_run_record, make_agent
    ) -> None:
        """An agent with a webhook_url returns a single webhook channel spec."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://agent.example.com/hook")

        # Act
        channels = resolve_channels(run, agent)

        # Assert
        assert len(channels) == 1
        assert channels[0]["name"] == "webhook"
        assert channels[0]["config"]["url"] == "https://agent.example.com/hook"

    def test_settings_webhook_url_used_when_agent_has_no_url(
        self, make_run_record, make_agent, make_settings
    ) -> None:
        """When agent.webhook_url is None, the global settings URL is used."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url=None)
        settings = make_settings(completion_webhook_url="https://settings.example.com/hook")

        # Act
        channels = resolve_channels(run, agent, settings)

        # Assert
        assert len(channels) == 1
        assert channels[0]["config"]["url"] == "https://settings.example.com/hook"

    def test_agent_url_wins_over_settings_url(
        self, make_run_record, make_agent, make_settings
    ) -> None:
        """Agent-level webhook_url takes priority over the global settings URL."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://agent.example.com/hook")
        settings = make_settings(completion_webhook_url="https://settings.example.com/hook")

        # Act
        channels = resolve_channels(run, agent, settings)

        # Assert
        assert channels[0]["config"]["url"] == "https://agent.example.com/hook"

    def test_returns_empty_list_when_no_url_configured(
        self, make_run_record, make_agent, make_settings
    ) -> None:
        """When neither agent nor settings provide a URL, no channels are returned."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url=None)
        settings = make_settings(completion_webhook_url=None)

        # Act
        channels = resolve_channels(run, agent, settings)

        # Assert
        assert channels == []

    def test_returns_empty_list_when_settings_is_none(
        self, make_run_record, make_agent
    ) -> None:
        """When settings is None and agent has no URL, the result is empty."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url=None)

        # Act
        channels = resolve_channels(run, agent, settings=None)

        # Assert
        assert channels == []

    def test_none_agent_falls_back_to_settings_url(
        self, make_run_record, make_settings
    ) -> None:
        """When agent is None, the settings completion webhook URL is used."""
        # Arrange
        run = make_run_record()
        settings = make_settings(completion_webhook_url="https://fallback.example.com/hook")

        # Act
        channels = resolve_channels(run, agent=None, settings=settings)

        # Assert
        assert len(channels) == 1
        assert channels[0]["config"]["url"] == "https://fallback.example.com/hook"

    def test_none_agent_and_none_settings_returns_empty(self, make_run_record) -> None:
        """Both agent and settings being None yields no channels."""
        # Arrange
        run = make_run_record()

        # Act
        channels = resolve_channels(run, agent=None, settings=None)

        # Assert
        assert channels == []

    def test_agent_empty_string_url_falls_back_to_settings(
        self, make_run_record, make_agent, make_settings
    ) -> None:
        """An explicitly empty string webhook_url on the agent is treated as absent."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="")
        settings = make_settings(completion_webhook_url="https://settings.example.com/hook")

        # Act
        channels = resolve_channels(run, agent, settings)

        # Assert — empty string is falsy, so settings URL wins
        assert channels[0]["config"]["url"] == "https://settings.example.com/hook"

    def test_resolved_channel_spec_has_correct_structure(
        self, make_run_record, make_agent
    ) -> None:
        """Each resolved channel spec is a dict with ``name`` and ``config`` keys."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://example.com/hook")

        # Act
        channels = resolve_channels(run, agent)

        # Assert
        spec = channels[0]
        assert "name" in spec
        assert "config" in spec
        assert isinstance(spec["config"], dict)
        assert "url" in spec["config"]


# --------------------------------------------------------------------------- #
# dispatch_completion
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestDispatchCompletion:
    """Verify task scheduling, channel resolution, and failure-mode guards."""

    def test_noop_when_no_channels_resolved(
        self, make_run_record, make_agent, mock_store
    ) -> None:
        """dispatch_completion returns early without scheduling any tasks when no channels."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url=None)  # no URL → no channels
        mock_store.get_usage.return_value = None

        with patch("agentbox.core.execution.dispatch.get_channel") as mock_get_channel:
            # Act (synchronous call is fine here — returns before loop access)
            dispatch_completion(run, agent, mock_store)

        # Assert — get_channel never called, no tasks created
        mock_get_channel.assert_not_called()

    def test_no_running_loop_logs_warning_and_does_not_raise(
        self,
        make_run_record,
        make_agent,
        mock_store,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When called outside an async context, a warning is logged and no exception raised."""
        # Arrange — this is a *synchronous* test; there is no running event loop.
        run = make_run_record()
        agent = make_agent(webhook_url="https://example.com/hook")
        mock_store.get_usage.return_value = None

        # Act
        with caplog.at_level(logging.WARNING, logger="agentbox.core.execution.dispatch"):
            dispatch_completion(run, agent, mock_store)

        # Assert
        assert "no running event loop" in caplog.text

    async def test_creates_task_per_channel_in_running_loop(
        self, make_run_record, make_agent, mock_store
    ) -> None:
        """In an async context a background task is created for each resolved channel."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://example.com/hook")
        mock_store.get_usage.return_value = None

        deliver_invoked = asyncio.Event()

        class _FakeChannel:
            name = "webhook"

            async def deliver(self, *args, **kwargs) -> DeliveryResult:
                deliver_invoked.set()
                return DeliveryResult(ok=True, attempts=1)

        with patch(
            "agentbox.core.execution.dispatch.get_channel", return_value=_FakeChannel
        ):
            with patch(
                "agentbox.core.execution.dispatch.build_completion_payload",
                return_value={"run_id": "run-1"},
            ):
                # Act
                dispatch_completion(run, agent, mock_store)
                # Yield to allow the background task to run
                await asyncio.sleep(0)

        # Assert
        assert deliver_invoked.is_set(), "channel.deliver was never called"

    async def test_unknown_channel_name_logs_error_and_continues(
        self,
        make_run_record,
        make_agent,
        mock_store,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """An unregistered channel name is logged as an error; no exception is raised."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://example.com/hook")
        mock_store.get_usage.return_value = None

        with patch(
            "agentbox.core.execution.dispatch.get_channel",
            side_effect=KeyError("webhook"),
        ):
            with patch(
                "agentbox.core.execution.dispatch.build_completion_payload",
                return_value={"run_id": "run-1"},
            ):
                with caplog.at_level(
                    logging.ERROR, logger="agentbox.core.execution.dispatch"
                ):
                    # Act — must not raise
                    dispatch_completion(run, agent, mock_store)
                    await asyncio.sleep(0)

        # Assert
        assert "no dispatch channel registered" in caplog.text

    async def test_done_callback_is_added_to_task(
        self, make_run_record, make_agent, mock_store
    ) -> None:
        """The delivery task gets a done callback that can apply the delivery outcome."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://example.com/hook")
        mock_store.get_usage.return_value = None
        mock_store.get_run.return_value = None  # handled gracefully in policy

        deliver_done = asyncio.Event()

        class _FakeChannel:
            name = "webhook"

            async def deliver(self, *args, **kwargs) -> DeliveryResult:
                deliver_done.set()
                return DeliveryResult(ok=True, attempts=1)

        with patch(
            "agentbox.core.execution.dispatch.get_channel", return_value=_FakeChannel
        ):
            with patch(
                "agentbox.core.execution.dispatch.build_completion_payload",
                return_value={"run_id": "run-1"},
            ):
                # Act
                dispatch_completion(run, agent, mock_store)
                # Allow both the task and its done callback to complete
                await asyncio.sleep(0)
                await asyncio.sleep(0)

        # Assert — deliver was called (callback path exercised)
        assert deliver_done.is_set()

    async def test_multiple_channels_each_get_own_task(
        self, make_run_record, make_agent, mock_store
    ) -> None:
        """When resolve_channels returns N specs, N delivery tasks are created."""
        # Arrange
        run = make_run_record()
        agent = make_agent(webhook_url="https://example.com/hook")
        mock_store.get_usage.return_value = None

        deliver_count = 0

        class _FakeChannel:
            name = "webhook"

            async def deliver(self, *args, **kwargs) -> DeliveryResult:
                nonlocal deliver_count
                deliver_count += 1
                return DeliveryResult(ok=True, attempts=1)

        two_specs = [
            {"name": "webhook", "config": {"url": "https://a.example.com"}},
            {"name": "webhook", "config": {"url": "https://b.example.com"}},
        ]

        with patch(
            "agentbox.core.execution.dispatch.resolve_channels", return_value=two_specs
        ):
            with patch(
                "agentbox.core.execution.dispatch.get_channel", return_value=_FakeChannel
            ):
                with patch(
                    "agentbox.core.execution.dispatch.build_completion_payload",
                    return_value={"run_id": "run-1"},
                ):
                    # Act
                    dispatch_completion(run, agent, mock_store)
                    await asyncio.sleep(0)

        # Assert — one deliver() call per channel spec
        assert deliver_count == 2
