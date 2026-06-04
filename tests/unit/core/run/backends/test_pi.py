"""Tests for the pi backend adapter (Plan 16 Phase 2)."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data import TextEvent, ThinkingEvent, UsageEvent
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.constants import RunnerKind
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.backends.pi import (
    PiBackend,
    build_pi_argv,
    parse_pi_event,
)

DEFAULT_RUNNER = RunnerSpec(kind=RunnerKind.PI, extra_args=[])


def _agent(**overrides: object) -> AgentDef:
    kwargs = {"id": "pi_agent", "runner": DEFAULT_RUNNER}
    kwargs.update(overrides)
    return AgentDef(**kwargs)  # type: ignore[arg-type]


def test_render_produces_expected_argv() -> None:
    rendered = PiBackend().render(_agent(), Path("/tmp/wd"))
    assert rendered.argv[:4] == ["pi", "-p", "--mode", "json"]


def test_render_passes_effective_model_when_set() -> None:
    agent = _agent()
    rendered = PiBackend().render(
        agent,
        Path("/tmp/wd"),
        runner_config=EffectiveRunnerConfig(backend="pi", model="pi-1"),
    )
    idx = rendered.argv.index("--model")
    assert rendered.argv[idx + 1] == "pi-1"


def test_build_pi_argv_uses_default_when_no_spec_model() -> None:
    argv = build_pi_argv(None, [], default_model="pi-default")
    idx = argv.index("--model")
    assert argv[idx + 1] == "pi-default"


def test_build_pi_argv_skips_default_when_extra_args_has_model() -> None:
    argv = build_pi_argv(None, ["--model", "custom"], default_model="pi-default")
    assert argv.count("--model") == 1
    assert "custom" in argv and "pi-default" not in argv


def test_parse_pi_event_text() -> None:
    events, sid = parse_pi_event({"type": "text", "text": "hello"}, "rid")
    assert sid is None
    assert isinstance(events[0], TextEvent) and events[0].text == "hello"


def test_parse_pi_event_thinking() -> None:
    events, _sid = parse_pi_event({"type": "thinking", "text": "..."}, "rid")
    assert any(isinstance(e, ThinkingEvent) for e in events)


def test_parse_pi_event_usage() -> None:
    events, _sid = parse_pi_event(
        {
            "type": "usage",
            "model": "pi-1",
            "input_tokens": 5,
            "output_tokens": 9,
        },
        "rid",
    )
    usage = [e for e in events if isinstance(e, UsageEvent)]
    assert usage and usage[0].input_tokens == 5 and usage[0].output_tokens == 9


def test_parse_pi_event_session_id() -> None:
    _events, sid = parse_pi_event({"type": "session", "id": "s-1"}, "rid")
    assert sid == "s-1"


def test_digest_stable_across_identical_inputs() -> None:
    a = _agent()
    backend = PiBackend()
    assert (
        backend.render(a, Path("/tmp/wd")).digest
        == backend.render(a, Path("/tmp/wd")).digest
    )


def test_parse_pi_event_ignores_unknown() -> None:
    events, sid = parse_pi_event({"type": "noise"}, "rid")
    assert events == [] and sid is None
