"""Tests for the Codex backend adapter (Plan 16 Phase 2)."""

from __future__ import annotations

from pathlib import Path

from agentbox.api.events import TextEvent, UsageEvent
from agentbox.core.agent.profiles import EffectiveRunnerConfig
from agentbox.core.constants import RunnerKind
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.run.backends.codex import (
    CodexBackend,
    build_codex_argv,
    parse_codex_event,
)

DEFAULT_RUNNER = RunnerSpec(kind=RunnerKind.CODEX, extra_args=[])


def _agent(**overrides: object) -> AgentDef:
    kwargs = {"id": "codex_agent", "runner": DEFAULT_RUNNER}
    kwargs.update(overrides)
    return AgentDef(**kwargs)  # type: ignore[arg-type]


def test_render_produces_expected_argv() -> None:
    rendered = CodexBackend().render(_agent(), Path("/tmp/wd"))
    assert rendered.argv[:3] == ["codex", "exec", "--json"]


def test_render_passes_effective_model_when_set() -> None:
    agent = _agent()
    rendered = CodexBackend().render(
        agent,
        Path("/tmp/wd"),
        runner_config=EffectiveRunnerConfig(backend="codex", model="o4-mini"),
    )
    idx = rendered.argv.index("--model")
    assert rendered.argv[idx + 1] == "o4-mini"


def test_render_appends_effective_extra_args() -> None:
    agent = _agent()
    rendered = CodexBackend().render(
        agent,
        Path("/tmp/wd"),
        runner_config=EffectiveRunnerConfig(
            backend="codex", extra_args=["--cwd", "/x"]
        ),
    )
    assert "--cwd" in rendered.argv and "/x" in rendered.argv


def test_digest_stable_across_identical_inputs() -> None:
    a = _agent()
    backend = CodexBackend()
    r1 = backend.render(a, Path("/tmp/wd"))
    r2 = backend.render(a, Path("/tmp/wd"))
    assert r1.digest == r2.digest


def test_build_codex_argv_uses_default_when_no_spec_model() -> None:
    argv = build_codex_argv(None, [], default_model="o4-mini-default")
    idx = argv.index("--model")
    assert argv[idx + 1] == "o4-mini-default"


def test_build_codex_argv_skips_default_when_extra_args_has_model() -> None:
    argv = build_codex_argv(
        None, ["--model", "custom"], default_model="o4-mini-default"
    )
    # Only one --model expected (the one inside extra_args)
    assert argv.count("--model") == 1
    assert "custom" in argv and "o4-mini-default" not in argv


def test_parse_codex_event_assistant_text() -> None:
    evt = {
        "type": "item.completed",
        "item": {"item_type": "assistant_message", "text": "hello"},
    }
    events, sid = parse_codex_event(evt, "rid")
    assert sid is None
    assert len(events) == 1
    assert isinstance(events[0], TextEvent) and events[0].text == "hello"
    assert events[0].delta is True


def test_parse_codex_event_thread_started_captures_sid() -> None:
    evt = {"type": "thread.started", "thread_id": "thr-1"}
    events, sid = parse_codex_event(evt, "rid")
    assert events == []
    assert sid == "thr-1"


def test_parse_codex_event_usage() -> None:
    evt = {
        "type": "turn.completed",
        "model": "o4-mini",
        "usage": {"input_tokens": 12, "output_tokens": 34, "cached_input_tokens": 7},
    }
    events, _sid = parse_codex_event(evt, "rid")
    usage = [e for e in events if isinstance(e, UsageEvent)]
    assert usage and usage[0].input_tokens == 12
    assert usage[0].output_tokens == 34
    assert usage[0].cache_read_tokens == 7
    assert usage[0].model == "o4-mini"


def test_parse_codex_event_ignores_unknown() -> None:
    events, sid = parse_codex_event({"type": "noise"}, "rid")
    assert events == [] and sid is None
