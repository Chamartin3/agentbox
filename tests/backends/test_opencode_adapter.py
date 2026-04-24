"""Tests for the OpenCode backend adapter."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.backends.opencode import OpenCodeBackend
from agentbox.core.constants import RunnerKind
from agentbox.core.data.manifest import AgentDef, RunnerSpec

DEFAULT_RUNNER = RunnerSpec(
    kind=RunnerKind.OPENCODE,
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


def test_render_includes_extra_args() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "--agent" in rendered.argv
    assert "test-agent" in rendered.argv


def test_render_applies_default_model_when_missing() -> None:
    agent = _make_agent(runner=RunnerSpec(kind=RunnerKind.OPENCODE, extra_args=[]))
    adapter = OpenCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "--model" in rendered.argv


def test_render_does_not_override_explicit_model_in_extra_args() -> None:
    agent = _make_agent(
        runner=RunnerSpec(
            kind=RunnerKind.OPENCODE,
            extra_args=["--model", "my-custom-model"],
        )
    )
    adapter = OpenCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    model_idx = rendered.argv.index("--model")
    assert rendered.argv[model_idx + 1] == "my-custom-model"


def test_digest_stable_across_identical_inputs() -> None:
    agent = _make_agent()
    adapter = OpenCodeBackend()
    r1 = adapter.render(agent, Path("/tmp/workdir"))
    r2 = adapter.render(agent, Path("/tmp/workdir"))

    assert r1.digest == r2.digest


def test_digest_changes_when_extra_args_change() -> None:
    adapter = OpenCodeBackend()

    agent_a = _make_agent(
        runner=RunnerSpec(kind=RunnerKind.OPENCODE, extra_args=["--agent", "a"])
    )
    agent_b = _make_agent(
        runner=RunnerSpec(kind=RunnerKind.OPENCODE, extra_args=["--agent", "b"])
    )

    r_a = adapter.render(agent_a, Path("/tmp/workdir"))
    r_b = adapter.render(agent_b, Path("/tmp/workdir"))

    assert r_a.digest != r_b.digest
