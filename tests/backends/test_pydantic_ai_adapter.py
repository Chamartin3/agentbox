"""Tests for the PydanticAI backend adapter."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.backends.pydantic_ai import PydanticAiBackend
from agentbox.core.constants import RunnerKind
from agentbox.core.data.manifest import AgentDef, RunnerSpec


DEFAULT_RUNNER = RunnerSpec(kind=RunnerKind.PYDANTIC_AI)


def _make_agent(**overrides: object) -> AgentDef:
    kwargs = dict(
        id="test_agent",
        runner=DEFAULT_RUNNER,
    )
    kwargs.update(overrides)
    return AgentDef(**kwargs)  # type: ignore[arg-type]


def test_render_returns_minimal_config() -> None:
    agent = _make_agent()
    adapter = PydanticAiBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert rendered.argv == []
    assert rendered.env == {}
    assert rendered.cwd == Path(".")


def test_render_stores_agent_meta() -> None:
    agent = _make_agent(
        runner=RunnerSpec(
            kind=RunnerKind.PYDANTIC_AI,
            agent_module="my_module:MyAgent",
        )
    )
    adapter = PydanticAiBackend()
    rendered = adapter.render(agent, Path("/tmp/workdir"))

    assert rendered.agent_meta.get("agent_module") == "my_module:MyAgent"
    assert rendered.agent_meta.get("agent_id") == "test_agent"


def test_render_stores_prompt_text(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("You are a helpful assistant.")
    agent = _make_agent(
        prompt_path=str(prompt_file),
    )
    adapter = PydanticAiBackend()
    rendered = adapter.render(agent, tmp_path)

    assert "helpful assistant" in rendered.agent_meta.get("prompt", "")


def test_digest_stable_across_identical_inputs() -> None:
    agent = _make_agent()
    adapter = PydanticAiBackend()
    r1 = adapter.render(agent, Path("/tmp/workdir"))
    r2 = adapter.render(agent, Path("/tmp/workdir"))

    assert r1.digest == r2.digest


def test_digest_changes_when_agent_module_changes() -> None:
    adapter = PydanticAiBackend()

    agent_a = _make_agent(
        runner=RunnerSpec(
            kind=RunnerKind.PYDANTIC_AI,
            agent_module="mod_a:AgentA",
        )
    )
    agent_b = _make_agent(
        runner=RunnerSpec(
            kind=RunnerKind.PYDANTIC_AI,
            agent_module="mod_b:AgentB",
        )
    )

    r_a = adapter.render(agent_a, Path("/tmp/workdir"))
    r_b = adapter.render(agent_b, Path("/tmp/workdir"))

    assert r_a.digest != r_b.digest
