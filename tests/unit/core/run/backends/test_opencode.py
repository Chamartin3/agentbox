"""Tests for the OpenCode backend adapter."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.db import AgentDef, RunnerSpec
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


def test_effective_model_is_passed_even_when_agent_has_legacy_model() -> None:
    agent = _make_agent(runner=RunnerSpec(kind="claude_code", model="haiku"))
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
    assert "haiku" not in rendered.argv
