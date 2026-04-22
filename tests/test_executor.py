"""End-to-end: subprocess runner through the executor, with a guardrail."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agentbox.config import Settings
from agentbox.core.definitions import AgentDef, GuardrailRef, RunnerSpec
from agentbox.core.executor import RunExecutor
from agentbox.core.guardrails.base import Guardrail, GuardrailContext, GuardrailResult
from agentbox.core.session_store import SessionStore, read_transcript


class _Echo(Guardrail):
    name = "echo"

    def evaluate(self, ctx: GuardrailContext) -> GuardrailResult:
        return GuardrailResult(ok="hello" in ctx.output, message=ctx.output[:50])


def test_executor_runs_subprocess(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        project_root=tmp_path,
        port=0,
        host="127.0.0.1",
        workspaces_root=tmp_path / "ws",
    )
    store = SessionStore(settings.db_path)
    executor = RunExecutor(store, settings)

    # Inject a fake guardrail plugin
    import agentbox.core.plugins as plugins

    plugins._GUARDRAIL_CLASSES = {"echo": _Echo}  # type: ignore[attr-defined]

    agent = AgentDef(
        id="t",
        runner=RunnerSpec(kind="subprocess", command=["/bin/sh", "-c", "echo hello"]),
        guardrails=[GuardrailRef(name="echo")],
    )

    async def go() -> str:
        rid = await executor.execute(agent, input_="ignored")
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
    assert len(grs) == 1 and grs[0]["name"] == "echo"
    # Transcript should contain at least a Done event.
    evs = read_transcript(Path(rec.transcript_path))
    assert any(e["type"] == "done" for e in evs)
