"""Tests for the pi backend adapter (Plan 16 Phase 2)."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data.events import TextEvent, ThinkingEvent, UsageEvent
from agentbox.core.engines.profiles import EffectiveRunnerConfig
from agentbox.core.data import AgentDef, RunnerSpec
from agentbox.core.engines.backends.pi import (
    PiBackend,
    build_pi_argv,
    parse_pi_event,
)

DEFAULT_RUNNER = RunnerSpec(kind="pi", extra_args=[])


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
    events, sid = parse_pi_event(
        {"type": "message_update",
         "assistantMessageEvent": {"type": "text_delta", "delta": "hello"}},
        "rid",
    )
    assert sid is None
    assert isinstance(events[0], TextEvent) and events[0].text == "hello"


def test_parse_pi_event_thinking() -> None:
    events, _sid = parse_pi_event(
        {"type": "message_update",
         "assistantMessageEvent": {"type": "thinking_delta", "delta": "..."}},
        "rid",
    )
    assert any(isinstance(e, ThinkingEvent) for e in events)


def test_parse_pi_event_usage() -> None:
    events, _sid = parse_pi_event(
        {"type": "turn_end",
         "message": {"role": "assistant", "model": "pi-1",
                     "usage": {"input": 5, "output": 9}}},
        "rid",
    )
    usage = [e for e in events if isinstance(e, UsageEvent)]
    assert usage and usage[0].input_tokens == 5 and usage[0].output_tokens == 9


def test_parse_pi_event_tool_call_and_result() -> None:
    from agentbox.core.data.events import ToolCallEvent, ToolResultEvent

    call, _ = parse_pi_event(
        {"type": "tool_execution_start", "toolCallId": "c1",
         "toolName": "read", "args": {"path": "note.txt"}},
        "rid",
    )
    assert isinstance(call[0], ToolCallEvent)
    assert call[0].tool == "read" and call[0].arguments == {"path": "note.txt"}

    res, _ = parse_pi_event(
        {"type": "tool_execution_end", "toolCallId": "c1", "toolName": "read",
         "result": {"content": [{"type": "text", "text": "secret WIDGET"}]},
         "isError": False},
        "rid",
    )
    assert isinstance(res[0], ToolResultEvent)
    assert res[0].ok and "WIDGET" in res[0].result_excerpt


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
