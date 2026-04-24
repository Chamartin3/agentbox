"""Smoke tests — imports + manifest parsing + executor wiring."""

from __future__ import annotations

from pathlib import Path


def test_imports(isolated_data_dir: Path) -> None:
    from agentbox.api.app import create_app
    from agentbox.api.events import DoneEvent, ToolCallEvent, UsageEvent
    from agentbox.core.data import SessionStore
    from agentbox.core.definitions import AgentDef, DefinitionLoader, RunnerSpec
    from agentbox.core.executor import RunExecutor

    assert create_app() is not None
    assert DoneEvent(run_id="x", ok=True).type == "done"
    assert ToolCallEvent(run_id="x", tool="t", arguments={}).type == "tool_call"
    assert UsageEvent(run_id="x").type == "usage"
    assert RunnerSpec(kind="claude_code").kind == "claude_code"
    _ = AgentDef, DefinitionLoader, RunExecutor, SessionStore


def test_manifest_parses(tmp_path: Path) -> None:
    from agentbox.core.definitions import DefinitionLoader

    (tmp_path / "agentbox.toml").write_text(
        """
project = "demo"

[[agents]]
id = "echo"
description = "echo"
session_mode = "headless"

  [agents.runner]
  kind = "claude_code"
  model = "haiku"
  extra_args = ["--print"]
"""
    )
    loader = DefinitionLoader(tmp_path)
    m = loader.load()
    assert m.project == "demo"
    assert len(m.agents) == 1
    assert m.agents[0].id == "echo"
    assert m.agents[0].runner.kind == "claude_code"
    assert m.agents[0].runner.model == "haiku"
    assert m.agents[0].runner.extra_args == ["--print"]


def test_session_store(tmp_path: Path) -> None:
    from agentbox.core.data import SessionStore

    store = SessionStore(tmp_path / "db.sqlite")
    rid = store.create_run("a", "in", str(tmp_path), str(tmp_path / "t.jsonl"))
    store.record_usage(
        rid, {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.001}
    )
    store.record_usage(rid, {"input_tokens": 5})
    u = store.get_usage(rid)
    assert u and u["input_tokens"] == 15 and u["output_tokens"] == 20
    store.finish_run(rid, ok=True, output="hello")
    rec = store.get_run(rid)
    assert rec and rec.status == "ok" and rec.output == "hello"
    assert store.aggregate_usage()["runs"] == 1
