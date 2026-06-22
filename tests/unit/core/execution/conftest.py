"""Shared fixtures for execution unit tests.

Hoists the near-duplicate ``_SlowBackend`` fake that was defined in both
``test_retry.py`` and ``orchestrate/test_timeout_budget.py`` into a single
factory fixture. The backend sleeps before completing so tests can drive the
shared-deadline / timeout paths.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from agentbox.core.db import DoneEvent, RunEvent, TextEvent
from agentbox.core.engines.contracts.base import BackendAdapter, RenderedConfig


@pytest.fixture
def make_slow_backend() -> Callable[..., BackendAdapter]:
    """Factory for a backend that sleeps then emits shaped output + Done.

    Pair a long sleep with a tight deadline to assert the attempt is cancelled
    at the shared budget rather than after a per-attempt window.
    """

    def _make(sleep_s: float = 5.0, output: str = "{}") -> BackendAdapter:
        class _SlowBackend(BackendAdapter):
            name = "test-slow"

            def render(self, agent, workdir, **kw) -> RenderedConfig:  # type: ignore[no-untyped-def]
                return RenderedConfig()

            async def run(  # type: ignore[override]
                self, rendered: RenderedConfig, input: str, run_id: str
            ) -> AsyncIterator[RunEvent]:
                await asyncio.sleep(sleep_s)
                yield TextEvent(run_id=run_id, text=output, role="assistant")
                yield DoneEvent(run_id=run_id, ok=True)

        return _SlowBackend()

    return _make
