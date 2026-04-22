"""Executor guarantees `finish_run` is always called.

The earlier bug: if guardrails raised, or the executor task was cancelled
mid-run, the run row stayed at status='running' forever. The fix wraps
the body of `_run` in try/finally so finish_run executes no matter what.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import DoneEvent, RunEvent, TextEvent
from agentbox.config import load_settings
from agentbox.core.definitions import AgentDef, GuardrailRef, RunnerSpec
from agentbox.core.executor import RunExecutor
from agentbox.core.guardrails.base import Guardrail, GuardrailContext, GuardrailResult
from agentbox.core.runners.base import Runner, RunRequest
from agentbox.core.session_store import SessionStore


class _OkRunner(Runner):
    kind = "subprocess"

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        yield TextEvent(run_id=req.run_id, text="done")
        yield DoneEvent(run_id=req.run_id, ok=True)


class _BoomGuardrail(Guardrail):
    name = "boom"

    def evaluate(self, ctx: GuardrailContext) -> GuardrailResult:  # noqa: ARG002
        raise RuntimeError("guardrail crashed")


def _make_executor(tmp_path: Path) -> tuple[RunExecutor, SessionStore]:
    import os

    os.environ["AGENTBOX_DATA_DIR"] = str(tmp_path)
    os.environ["AGENTBOX_PROJECT_ROOT"] = str(tmp_path)
    settings = load_settings()
    store = SessionStore(settings.db_path)
    return RunExecutor(store, settings), store


def _drain(executor: RunExecutor, rid: str) -> None:
    """Block until the broadcaster closes, signalling _run finished."""
    b = executor.broadcaster(rid)
    assert b is not None
    q = b.subscribe()

    async def pump() -> None:
        while await q.get() is not None:
            pass

    asyncio.get_event_loop().run_until_complete(pump())


def test_finish_run_called_when_guardrail_raises(tmp_path: Path) -> None:
    """If a guardrail's evaluate() raises, the run still terminates cleanly."""
    executor, store = _make_executor(tmp_path)

    import agentbox.core.plugins as plugins

    plugins.runners()  # force-load entrypoints into the cache
    plugins._RUNNER_CLASSES["subprocess"] = _OkRunner  # type: ignore[index]
    plugins._GUARDRAIL_CLASSES = {"boom": _BoomGuardrail}  # type: ignore[attr-defined]

    agent = AgentDef(
        id="t",
        runner=RunnerSpec(kind="subprocess", command=["true"]),
        guardrails=[GuardrailRef(name="boom")],
    )

    async def go() -> str:
        rid = await executor.execute(agent, input_="x")
        b = executor.broadcaster(rid)
        assert b is not None
        q = b.subscribe()
        while await q.get() is not None:
            pass
        return rid

    rid = asyncio.run(go())
    rec = store.get_run(rid)
    assert rec is not None, "run row must exist"
    assert rec.finished_at is not None, "finish_run must have been called"
    # Runner succeeded so status is 'ok' — guardrail exception is captured
    # as auxiliary error text but doesn't fail the run itself.
    assert rec.status == "ok"
    assert rec.error is not None and "guardrail" in rec.error.lower()


def test_finish_run_called_when_runner_raises(tmp_path: Path) -> None:
    """Runner blowing up still terminates the row (status='error')."""

    class _BoomRunner(Runner):
        kind = "subprocess"

        async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
            if False:  # pragma: no cover - generator protocol
                yield  # type: ignore[unreachable]
            raise RuntimeError("runner exploded")

    executor, store = _make_executor(tmp_path)

    import agentbox.core.plugins as plugins

    plugins.runners()
    plugins._RUNNER_CLASSES["subprocess"] = _BoomRunner  # type: ignore[index]

    agent = AgentDef(id="t", runner=RunnerSpec(kind="subprocess", command=["true"]))

    async def go() -> str:
        rid = await executor.execute(agent, input_="x")
        b = executor.broadcaster(rid)
        assert b is not None
        q = b.subscribe()
        while await q.get() is not None:
            pass
        return rid

    rid = asyncio.run(go())
    rec = store.get_run(rid)
    assert rec is not None
    assert rec.finished_at is not None, "finish_run must run even on runner crash"
    assert rec.status == "error"
    assert rec.error is not None and "exploded" in rec.error
