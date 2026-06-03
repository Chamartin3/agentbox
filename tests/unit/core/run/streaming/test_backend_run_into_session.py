"""Tests for ``BackendAdapter.run_into_session()`` — the iterator bridge.

The default implementation pumps the legacy
``run() -> AsyncIterator[RunEvent]`` contract into the central
``RunStreamSession``. These tests pin down the bridge's contract:
content events go through ``session.emit()``, ``DoneEvent`` is
captured into the returned ``BackendRunResult`` and NOT emitted —
the executor handles the final emit after validation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from agentbox.core.data import DoneEvent, LogEvent, RunEvent, TextEvent
from agentbox.core.engines.backends.base import (
    BackendAdapter,
    BackendRunResult,
    RenderedConfig,
)
from agentbox.core.execution.streaming.session import CaptureSession


class _IteratorBackend(BackendAdapter):
    """Test backend that yields a scripted sequence of events."""

    name = "test-iterator"

    def __init__(self, events: list[RunEvent]) -> None:
        self._events = events

    def render(  # type: ignore[no-untyped-def]
        self, agent, workdir, mcp_tools=None, creds=None, runner_config=None
    ) -> RenderedConfig:
        return RenderedConfig()

    async def run(  # type: ignore[override]
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        for ev in self._events:
            yield ev


@pytest.mark.asyncio
async def test_content_events_go_through_session() -> None:
    """``run()``-yielded non-Done events reach the session."""
    events = [
        LogEvent(run_id="r", level="info", message="start"),
        TextEvent(run_id="r", text="hello", role="assistant"),
        DoneEvent(run_id="r", ok=True),
    ]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        result = await backend.run_into_session(RenderedConfig(), "input", session)

    # DoneEvent was NOT emitted — the executor owns the final emit.
    assert [type(e) for e in session.captured] == [LogEvent, TextEvent]
    # Terminal status was extracted into the result.
    assert result == BackendRunResult(ok=True)


@pytest.mark.asyncio
async def test_done_with_error_captured() -> None:
    """A failing DoneEvent surfaces as a failing BackendRunResult."""
    events = [
        DoneEvent(run_id="r", ok=False, error="boom", status="error", exit_code=1),
    ]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        result = await backend.run_into_session(RenderedConfig(), "input", session)

    assert result.ok is False
    assert result.error == "boom"
    assert result.status == "error"
    assert result.exit_code == 1
    # Nothing emitted — the only event in the iterator was the DoneEvent
    # we're suppressing.
    assert session.captured == []


@pytest.mark.asyncio
async def test_assistant_text_lands_in_session_output_text() -> None:
    """The session's accumulator picks up assistant text via the bridge."""
    events = [
        TextEvent(run_id="r", text="chunk1", role="assistant"),
        TextEvent(run_id="r", text="delta", role="assistant", delta=True),
        TextEvent(run_id="r", text="chunk2", role="assistant"),
        DoneEvent(run_id="r", ok=True),
    ]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        await backend.run_into_session(RenderedConfig(), "input", session)

    # Non-delta assistant text accumulates; delta is UI-only.
    assert session.output_text == ["chunk1", "chunk2"]


@pytest.mark.asyncio
async def test_backend_with_no_done_event_returns_default_failure() -> None:
    """Misbehaved backends that never yield Done end up as ``ok=False``.

    The previous architecture relied on the executor's synthesized
    final DoneEvent to mask this; the new contract makes it explicit.
    """
    events = [LogEvent(run_id="r", level="info", message="hi")]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        result = await backend.run_into_session(RenderedConfig(), "input", session)

    assert result.ok is False
    assert [type(e) for e in session.captured] == [LogEvent]


class _DirectBackend(BackendAdapter):
    """Backend that overrides ``run_into_session`` instead of ``run``.

    The future migration target — backends call ``session.emit()``
    directly and return their status, with no iterator overhead.
    """

    name = "test-direct"

    def render(self, agent, workdir, mcp_tools=None, creds=None, runner_config=None):  # type: ignore[no-untyped-def]
        return RenderedConfig()

    async def run(  # type: ignore[override]
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        # Unused — kept only to satisfy the abstract method on the ABC.
        if False:
            yield  # pragma: no cover

    async def run_into_session(
        self,
        rendered: RenderedConfig,
        input: str,
        session,  # type: ignore[no-untyped-def]
    ) -> BackendRunResult:
        session.emit(LogEvent(run_id=session.run_id, level="info", message="direct"))
        return BackendRunResult(ok=True)


@pytest.mark.asyncio
async def test_direct_override_skips_iterator() -> None:
    """Backends migrated past the bridge work the same way."""
    backend = _DirectBackend()
    with CaptureSession(run_id="r") as session:
        result = await backend.run_into_session(RenderedConfig(), "input", session)

    assert result == BackendRunResult(ok=True)
    assert len(session.captured) == 1
    assert isinstance(session.captured[0], LogEvent)
