"""End-to-end: executor renders a fake backend, runs it, and persists state."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import DoneEvent, RunEvent, TextEvent
from agentbox.config import Settings
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.data import SessionStore, read_transcript
from agentbox.core.definitions import (
    AgentDef,
    DefinitionLoader,
    GuardrailRef,
    RunnerSpec,
)
from agentbox.core.executor import RunExecutor
from agentbox.core.guardrails.base import Guardrail, GuardrailContext, GuardrailResult


class _EchoAdapter:
    """Minimal BackendAdapter — yields a TextEvent then a successful DoneEvent."""

    name = "echo_backend"

    def render(self, agent, workdir, mcp_tools=None, creds=None, runner_config=None):  # type: ignore[no-untyped-def]
        return RenderedConfig(argv=["true"], cwd=workdir)

    async def run(
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        yield TextEvent(run_id=run_id, text="hello")
        yield DoneEvent(run_id=run_id, ok=True, output="hello")


class _ContainsHello(Guardrail):
    name = "echo"

    def evaluate(self, ctx: GuardrailContext) -> GuardrailResult:
        return GuardrailResult(ok="hello" in ctx.output, message=ctx.output[:50])


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        manifest_path=tmp_path / "manifest.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        agents_bundle_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
    )


def _register(name: str, adapter_cls: type) -> None:
    import agentbox.core.plugins as plugins

    plugins.backends()  # warm cache
    plugins._BACKEND_CLASSES[name] = adapter_cls  # type: ignore[index]


def test_executor_runs_and_invokes_guardrail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    settings = _settings(tmp_path)
    store = SessionStore(settings.db_path)
    executor = RunExecutor(store, settings, DefinitionLoader(settings.project_root))

    _register("echo_backend", _EchoAdapter)

    import agentbox.core.plugins as plugins

    plugins._GUARDRAIL_CLASSES = {"echo": _ContainsHello}  # type: ignore[attr-defined]

    agent = AgentDef(
        id="t",
        runner=RunnerSpec(kind="claude_code"),  # ignored — backend override wins
        guardrails=[GuardrailRef(name="echo")],
    )

    async def go() -> str:
        rid = await executor.execute(agent, input_="ignored", backend="echo_backend")
        b = executor.broadcaster(rid)
        assert b is not None
        q = b.subscribe()
        while await q.get() is not None:
            pass
        return rid

    rid = asyncio.run(go())
    rec = store.get_run(rid)
    assert rec is not None and rec.status == "ok"
    grs = store.list_guardrails(rid)
    assert len(grs) == 1 and grs[0]["name"] == "echo" and grs[0]["ok"]
    evs = read_transcript(Path(rec.transcript_path))
    assert any(e["type"] == "done" for e in evs)
    assert any(e["type"] == "text" and e["text"] == "hello" for e in evs)
