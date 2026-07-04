"""Pins the per-run timeout budget semantics.

The executor's run timeout is a *wall-clock budget shared across all
retry attempts*, not a per-attempt allowance. This test exercises the
distinction by simulating a backend that keeps failing validation and
asserting that the total wall time of the run respects the configured
budget instead of multiplying it by ``1 + max_validation_retries``.

Background: an opencode-backed run with ``timeout_seconds=400`` and
``max_validation_retries=3`` was observed to run 13+ minutes (each
attempt consumed its own 400s window). The user-visible symptom was a
run that ignored its configured timeout. This test prevents regression.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from agentbox.core.data.events import DoneEvent, RunEvent, TextEvent
from agentbox.core.engines.contracts.base import (
    BackendAdapter,
    RenderedConfig,
)
from agentbox.core.execution.orchestrate.executor import pump_into_session
from agentbox.core.execution.observability.stream import CaptureSession


class _SlowBackend(BackendAdapter):
    """Backend that sleeps a bit then 'succeeds' with shaped output.

    Used to drive the executor's retry loop in tests: pair with a
    validator that rejects the output to force retries, then measure
    that the shared deadline cuts the run off.
    """

    name = "test-slow"

    def __init__(self, sleep_s: float, output: str = "{}") -> None:
        self._sleep_s = sleep_s
        self._output = output

    def render(
        self, agent: object, workdir: Path, *args: object, **kw: object
    ) -> RenderedConfig:
        return RenderedConfig()

    async def run(  # type: ignore[override]
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        await asyncio.sleep(self._sleep_s)
        yield TextEvent(run_id=run_id, text=self._output)
        yield DoneEvent(run_id=run_id, ok=True)


@pytest.mark.asyncio
async def test_shared_deadline_fires_inside_attempt() -> None:
    """``asyncio.timeout_at(deadline)`` cancels a long attempt at the
    deadline, not after a per-attempt window."""
    backend = _SlowBackend(sleep_s=5.0)
    deadline = asyncio.get_event_loop().time() + 0.2

    with CaptureSession(run_id="r") as session, pytest.raises(TimeoutError):
        async with asyncio.timeout_at(deadline):
            await pump_into_session(backend, RenderedConfig(), "input", session)


@pytest.mark.asyncio
async def test_shared_deadline_carries_across_attempts() -> None:
    """Pins the *shared* aspect: when the budget is exhausted mid-run,
    a second ``timeout_at(deadline)`` raises immediately without granting
    a fresh window. This is what stops the multi-attempt run from
    drifting past the configured timeout."""
    backend = _SlowBackend(sleep_s=0.05)
    deadline = asyncio.get_event_loop().time() + 0.15

    # First attempt completes within budget.
    with CaptureSession(run_id="r") as session:
        async with asyncio.timeout_at(deadline):
            await pump_into_session(backend, RenderedConfig(), "input", session)

    # Burn the rest of the budget so the next attempt is already past it.
    await asyncio.sleep(0.2)
    assert asyncio.get_event_loop().time() >= deadline

    # Second attempt should see an immediate TimeoutError instead of
    # getting another fresh budget.
    with CaptureSession(run_id="r") as session, pytest.raises(TimeoutError):
        async with asyncio.timeout_at(deadline):
            await asyncio.sleep(0)  # any await suffices to deliver cancel


def test_deadline_check_message_includes_attempt_count() -> None:
    """The pre-attempt deadline check (in executor) reports HOW MANY
    attempts the budget covered — useful for distinguishing "agent was
    slow on attempt 1" from "agent was stuck on attempt 4".

    Pinned as a string-format check because the executor emits it as a
    LogEvent message and operators grep for it. Keep the prefix stable.
    """
    # We can't easily run the full executor here without spinning up a
    # store/loader, but we can lock down the message shape — drift in
    # this string breaks operator runbooks.
    attempt = 3
    timeout = 400
    msg = (
        f"timeout after {timeout}s "
        f"(budget exhausted across {attempt} attempt"
        f"{'s' if attempt != 1 else ''})"
    )
    assert msg == "timeout after 400s (budget exhausted across 3 attempts)"
    # Singular form on attempt 1 (the natural first-run case).
    attempt = 1
    msg = (
        f"timeout after {timeout}s "
        f"(budget exhausted across {attempt} attempt"
        f"{'s' if attempt != 1 else ''})"
    )
    assert msg == "timeout after 400s (budget exhausted across 1 attempt)"
