"""Tests for the OpenCode backend adapter."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.backends.opencode import OpenCodeBackend

DEFAULT_RUNNER = RunnerSpec(
    kind="opencode",
    extra_args=["--agent", "test-agent"],
)


def _make_agent(**overrides: object) -> AgentDef:
    kwargs = {
        "id": "test_agent",
        "runner": DEFAULT_RUNNER,
    }
    kwargs.update(overrides)
    return AgentDef(**kwargs)  # type: ignore[arg-type]


def test_render_produces_expected_argv() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "opencode" in rendered.argv
    assert "run" in rendered.argv
    assert "--dangerously-skip-permissions" in rendered.argv
    assert "--format" in rendered.argv
    assert "json" in rendered.argv


def test_render_sets_pwd_env() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/test_workdir"))

    assert rendered.env.get("PWD") == "/tmp/test_workdir"


def test_render_includes_effective_extra_args() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    rendered = adapter.render(
        agent,
        Path("/tmp/workdir"),
        runner_config=EffectiveRunnerConfig(
            backend="opencode", extra_args=["--agent", "test-agent"]
        ),
    )

    assert "--agent" in rendered.argv
    assert "test-agent" in rendered.argv


def test_tool_events_from_opencode_part() -> None:
    # Real opencode part shape captured from a qwen3 `read` tool call.
    from agentbox.core.engines.backends.opencode.stream import _tool_events

    part = {
        "type": "tool",
        "tool": "read",
        "callID": "call_hzf9by9w",
        "state": {
            "status": "completed",
            "input": {"filePath": "note.txt"},
            "output": "The secret word is WIDGET.",
        },
    }
    evs = _tool_events("run1", part)
    assert [e.type for e in evs] == ["tool_call", "tool_result"]
    assert evs[0].tool == "read" and evs[0].arguments == {"filePath": "note.txt"}
    assert evs[0].call_id == "call_hzf9by9w"
    assert evs[1].ok and "WIDGET" in evs[1].result_excerpt

    # A still-running part yields only the call, no result yet.
    running = {"type": "tool", "tool": "read", "callID": "c1", "state": {"status": "running"}}
    assert [e.type for e in _tool_events("run1", running)] == ["tool_call"]


def test_render_injects_ollama_provider(tmp_path: Path) -> None:
    import json

    agent = _make_agent()
    adapter = OpenCodeBackend()
    rendered = adapter.render(
        agent,
        tmp_path,
        runner_config=EffectiveRunnerConfig(
            backend="opencode",
            provider="ollama",
            model="ollama:qwen3:8b",
            base_url="http://ollama-sample:11434/v1",
        ),
    )

    # model id translated ollama:qwen3:8b -> ollama/qwen3:8b for --model
    assert rendered.argv[rendered.argv.index("--model") + 1] == "ollama/qwen3:8b"

    # provider block merged into opencode.json at workdir root
    cfg = json.loads((tmp_path / "opencode.json").read_text())
    ollama = cfg["provider"]["ollama"]
    assert ollama["npm"] == "ollama-ai-provider-v2"
    assert ollama["options"]["baseURL"] == "http://ollama-sample:11434/api"
    assert "qwen3:8b" in ollama["models"]


def test_render_applies_default_model_when_missing() -> None:
    agent = _make_agent(runner=RunnerSpec(kind="opencode", extra_args=[]))
    adapter = OpenCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "--model" in rendered.argv


def test_render_does_not_override_explicit_model_in_extra_args() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    rendered = adapter.render(
        agent,
        Path("/tmp/workdir"),
        runner_config=EffectiveRunnerConfig(
            backend="opencode",
            model="opencode/big-pickle",
            extra_args=["--model", "my-custom-model"],
        ),
    )

    model_idx = rendered.argv.index("--model")
    assert rendered.argv[model_idx + 1] == "my-custom-model"
    assert "opencode/big-pickle" not in rendered.argv


def test_digest_stable_across_identical_inputs() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    r1 = adapter.render(agent, Path("/tmp/workdir"))
    r2 = adapter.render(agent, Path("/tmp/workdir"))

    assert r1.digest == r2.digest


def test_digest_changes_when_effective_extra_args_change() -> None:
    adapter = OpenCodeBackend()
    agent = _make_agent()

    r_a = adapter.render(
        agent,
        Path("/tmp/workdir"),
        runner_config=EffectiveRunnerConfig(
            backend="opencode", extra_args=["--agent", "a"]
        ),
    )
    r_b = adapter.render(
        agent,
        Path("/tmp/workdir"),
        runner_config=EffectiveRunnerConfig(
            backend="opencode", extra_args=["--agent", "b"]
        ),
    )

    assert r_a.digest != r_b.digest


def test_effective_model_from_runner_config_is_passed() -> None:
    agent = _make_agent(runner=RunnerSpec(kind="claude_code"))
    adapter = OpenCodeBackend()
    rendered = adapter.render(
        agent,
        Path("/tmp/workdir"),
        runner_config=EffectiveRunnerConfig(
            backend="opencode", model="opencode/big-pickle"
        ),
    )

    model_idx = rendered.argv.index("--model")
    assert rendered.argv[model_idx + 1] == "opencode/big-pickle"
