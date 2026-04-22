"""Executor guarantees ``finish_run`` is always called.

The earlier bug: if guardrails raised, or the executor task was cancelled
mid-run, the run row stayed at ``status='running'`` forever. The fix wraps
the body of ``_run`` in try/finally so finish_run executes no matter what.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import DoneEvent, RunEvent, TextEvent
from agentbox.config import load_settings
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.data import SessionStore
from agentbox.core.definitions import AgentDef, DefinitionLoader, GuardrailRef, RunnerSpec
from agentbox.core.executor import RunExecutor
from agentbox.core.guardrails.base import Guardrail, GuardrailContext, GuardrailResult


class _OkAdapter:
    name = "fake"

    def render(self, agent, workdir, mcp_tools=None, creds=None):  # type: ignore[no-untyped-def]
        return RenderedConfig(argv=["true"], cwd=workdir)

    async def run(self, rendered, input, run_id):  # type: ignore[no-untyped-def]
        yield TextEvent(run_id=run_id, text="done")
        yield DoneEvent(run_id=run_id, ok=True)


class _BoomAdapter:
    name = "fake"

    def render(self, agent, workdir, mcp_tools=None, creds=None):  # type: ignore[no-untyped-def]
        return RenderedConfig(argv=["true"], cwd=workdir)

    async def run(self, rendered, input, run_id) -> AsyncIterator[RunEvent]:  # type: ignore[no-untyped-def]
        if False:  # pragma: no cover - generator protocol marker
            yield  # type: ignore[unreachable]
        raise RuntimeError("runner exploded")


class _BoomGuardrail(Guardrail):
    name = "boom"

    def evaluate(self, ctx: GuardrailContext) -> GuardrailResult:
        raise RuntimeError("guardrail crashed")


def _make_executor(tmp_path: Path) -> tuple[RunExecutor, SessionStore]:
    import os

    os.environ["AGENTBOX_DATA_DIR"] = str(tmp_path)
    os.environ["AGENTBOX_PROJECT_ROOT"] = str(tmp_path)
    os.environ["AGENTBOX_MANIFEST"] = str(tmp_path / "manifest.toml")
    settings = load_settings()
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(settings.project_root)
    return RunExecutor(store, settings, loader), store


def _register_backend(name: str, adapter_cls: type) -> None:
    import agentbox.core.plugins as plugins

    plugins.backends()
    plugins._BACKEND_CLASSES[name] = adapter_cls  # type: ignore[index]


def _drain_async(executor: RunExecutor, rid: str) -> None:
    b = executor.broadcaster(rid)
    assert b is not None
    q = b.subscribe()
    while q.get_nowait() is not None if False else True:
        try:
            ev = asyncio.get_event_loop().run_until_complete(q.get())
        except RuntimeError:
            break
        if ev is None:
            break


def test_finish_run_called_when_guardrail_raises(tmp_path: Path) -> None:
    """If a guardrail's evaluate() raises, the run still terminates cleanly."""
    executor, store = _make_executor(tmp_path)
    _register_backend("fake", _OkAdapter)

    import agentbox.core.plugins as plugins

    plugins._GUARDRAIL_CLASSES = {"boom": _BoomGuardrail}  # type: ignore[attr-defined]

    agent = AgentDef(
        id="t",
        runner=RunnerSpec(kind="claude_code"),
        guardrails=[GuardrailRef(name="boom")],
    )

    async def go() -> str:
        rid = await executor.execute(agent, input_="x", backend="fake")
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
    # Adapter succeeded so status is 'ok' — guardrail exception is captured
    # as auxiliary error text but doesn't fail the run itself.
    assert rec.status == "ok"
    assert rec.error is not None and "guardrail" in rec.error.lower()


def test_finish_run_called_when_runner_raises(tmp_path: Path) -> None:
    """Adapter blowing up still terminates the row (status='error')."""
    executor, store = _make_executor(tmp_path)
    _register_backend("fake", _BoomAdapter)

    agent = AgentDef(id="t", runner=RunnerSpec(kind="claude_code"))

    async def go() -> str:
        rid = await executor.execute(agent, input_="x", backend="fake")
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
