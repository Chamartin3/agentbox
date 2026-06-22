"""Shared fixtures for dispatch unit tests.

Replaces the per-file ``_make_run`` / inline-``MagicMock`` setup that was
triplicated across ``test_policy.py``, ``test_dispatch.py``, and
``test_webhooks.py``. Collaborators (store, task, settings) are injected;
``make_run_record`` is the single RunRecord factory for the whole subtree.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from agentbox.core.db import AgentDef, RunRecord


@pytest.fixture
def make_run_record() -> Callable[..., RunRecord]:
    """Factory for a completed RunRecord; override any field via kwargs."""

    def _make(**overrides: object) -> RunRecord:
        defaults: dict = dict(
            id="run-1",
            agent_id="agent-1",
            session_id=None,
            status="ok",
            input="hello",
            output='{"result": 1}',
            error=None,
            workdir=None,
            transcript_path=None,
            created_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:01:00",
            validation_status="ok",
            validation_errors=None,
            schema_validated_via="json-schema",
        )
        defaults.update(overrides)
        return RunRecord(**defaults)

    return _make


@pytest.fixture
def make_agent() -> Callable[..., AgentDef]:
    """Factory for a minimal AgentDef with an optional webhook_url."""

    def _make(webhook_url: str | None = None) -> AgentDef:
        return AgentDef(id="agent-1", webhook_url=webhook_url)

    return _make


@pytest.fixture
def make_settings() -> Callable[..., MagicMock]:
    """Factory for a settings mock carrying a completion_webhook_url."""

    def _make(completion_webhook_url: str | None = None) -> MagicMock:
        settings = MagicMock()
        settings.completion_webhook_url = completion_webhook_url
        return settings

    return _make


@pytest.fixture
def mock_task() -> MagicMock:
    """A bare asyncio-Task-like mock for on_delivery_done tests."""
    return MagicMock()


@pytest.fixture
def mock_broadcaster() -> MagicMock:
    """MagicMock broadcaster for asserting published LogEvents in channel tests."""
    return MagicMock()
