"""Tests for ``pump_into_session()`` — the iterator bridge.

The execution-layer pump bridges the legacy
``run() -> AsyncIterator[RunEvent]`` contract into the central
``RunStreamSession``. These tests pin down the bridge's contract:
content events go through ``session.emit()``, ``DoneEvent`` is
captured into the returned ``BackendRunResult`` and NOT emitted —
the executor handles the final emit after validation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from agentbox.core.data.constants import LogLevel, RunStatus
from agentbox.core.data.events import DoneEvent, LogEvent, RunEvent, TextEvent
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.data import RenderedConfig
from agentbox.core.data import BackendRunResult
from agentbox.core.execution.retry import pump_into_session
from agentbox.core.execution.observability.stream import CaptureSession, RunStreamSession


class _IteratorBackend(BackendAdapter):
    """Test backend that yields a scripted sequence of events."""

    name = "test-iterator"

    def __init__(self, events: list[RunEvent]) -> None:
        self._events = events

    def render(
        self, agent: object, workdir: Path, *args: object, **kw: object
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
    events: list[RunEvent] = [
        LogEvent(run_id="r", level=LogLevel.INFO, message="start"),
        TextEvent(run_id="r", text="hello"),
        DoneEvent(run_id="r", ok=True),
    ]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        result = await pump_into_session(backend, RenderedConfig(), "input", session)

    # DoneEvent was NOT emitted — the executor owns the final emit.
    assert [type(e) for e in session.captured] == [LogEvent, TextEvent]
    # Terminal status was extracted into the result.
    assert result == BackendRunResult(ok=True)


@pytest.mark.asyncio
async def test_done_with_error_captured() -> None:
    """A failing DoneEvent surfaces as a failing BackendRunResult."""
    events: list[RunEvent] = [
        DoneEvent(run_id="r", ok=False, error="boom", status=RunStatus.ERROR, exit_code=1),
    ]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        result = await pump_into_session(backend, RenderedConfig(), "input", session)

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
    events: list[RunEvent] = [
        TextEvent(run_id="r", text="chunk1"),
        TextEvent(run_id="r", text="delta", delta=True),
        TextEvent(run_id="r", text="chunk2"),
        DoneEvent(run_id="r", ok=True),
    ]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        await pump_into_session(backend, RenderedConfig(), "input", session)

    # Non-delta assistant text accumulates; delta is UI-only.
    assert session.output_text == ["chunk1", "chunk2"]


@pytest.mark.asyncio
async def test_backend_with_no_done_event_returns_default_failure() -> None:
    """Misbehaved backends that never yield Done end up as ``ok=False``.

    The previous architecture relied on the executor's synthesized
    final DoneEvent to mask this; the new contract makes it explicit.
    """
    events: list[RunEvent] = [LogEvent(run_id="r", level=LogLevel.INFO, message="hi")]
    backend = _IteratorBackend(events)
    with CaptureSession(run_id="r") as session:
        result = await pump_into_session(backend, RenderedConfig(), "input", session)

    assert result.ok is False
    assert [type(e) for e in session.captured] == [LogEvent]


class _DirectBackend(BackendAdapter):
    """Backend that exposes ``run_into_session`` instead of using ``run``.

    The future migration target — backends call ``session.emit()``
    directly and return their status, with no iterator overhead.
    """

    name = "test-direct"

    def render(
        self, agent: object, workdir: Path, *args: object, **kw: object
    ) -> RenderedConfig:
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
        session: RunStreamSession,
    ) -> BackendRunResult:
        session.emit(LogEvent(run_id=session.run_id, level=LogLevel.INFO, message="direct"))
        return BackendRunResult(ok=True)


@pytest.mark.asyncio
async def test_direct_override_skips_iterator() -> None:
    """Backends that provide a direct pump hook work the same way."""
    backend = _DirectBackend()
    with CaptureSession(run_id="r") as session:
        result = await pump_into_session(backend, RenderedConfig(), "input", session)

    assert result == BackendRunResult(ok=True)
    assert len(session.captured) == 1
    assert isinstance(session.captured[0], LogEvent)
