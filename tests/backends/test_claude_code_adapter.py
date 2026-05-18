"""Tests for the Claude Code backend adapter."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.constants import RunnerKind
from agentbox.core.data.manifest import AgentDef, RunnerSpec
from agentbox.core.run.backends.claude_code import ClaudeCodeBackend

DEFAULT_RUNNER = RunnerSpec(
    kind=RunnerKind.CLAUDE_CODE,
    model="claude-sonnet-4-20250514",
    allowed_tools=["Read", "Grep", "Write"],
    extra_args=["--verbose"],
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
    adapter = ClaudeCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "claude" in rendered.argv
    assert "-p" in rendered.argv
    assert "--model" in rendered.argv
    assert "claude-sonnet-4-20250514" in rendered.argv
    assert "--output-format" in rendered.argv
    assert "json" in rendered.argv
    assert "--permission-mode" in rendered.argv
    assert "bypassPermissions" in rendered.argv


def test_render_excludes_model_when_not_set() -> None:
    agent = _make_agent(
        runner=RunnerSpec(kind=RunnerKind.CLAUDE_CODE, allowed_tools=[])
    )
    adapter = ClaudeCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "--model" not in rendered.argv


def test_render_includes_extra_args() -> None:
    agent = _make_agent()
    adapter = ClaudeCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "--verbose" in rendered.argv


def test_render_env_strips_anthropic_keys(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-secret")

    agent = _make_agent()
    adapter = ClaudeCodeBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert "ANTHROPIC_API_KEY" not in rendered.env
    assert "ANTHROPIC_AUTH_TOKEN" not in rendered.env


def test_digest_stable_across_identical_inputs() -> None:
    agent = _make_agent()
    adapter = ClaudeCodeBackend()
    r1 = adapter.render(agent, Path("/tmp/workdir"))
    r2 = adapter.render(agent, Path("/tmp/workdir"))

    assert r1.digest == r2.digest


def test_digest_changes_when_tool_added() -> None:
    adapter = ClaudeCodeBackend()

    agent_a = _make_agent(
        runner=RunnerSpec(kind=RunnerKind.CLAUDE_CODE, allowed_tools=["Read"])
    )
    agent_b = _make_agent(
        runner=RunnerSpec(kind=RunnerKind.CLAUDE_CODE, allowed_tools=["Read", "Grep"])
    )

    r_a = adapter.render(agent_a, Path("/tmp/workdir"))
    r_b = adapter.render(agent_b, Path("/tmp/workdir"))

    assert r_a.digest != r_b.digest
