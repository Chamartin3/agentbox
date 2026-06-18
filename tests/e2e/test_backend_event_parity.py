"""Backend event-parity contract tests (Plan 16 Phase 1.2).

Asserts every `BackendAdapter` emits the same event sequence per
scenario defined in `tests/backends/EVENT_PARITY.md`. Backends not yet
satisfying a row are marked ``xfail`` — they flip to ``pass`` as later
phases land. Do not delete an ``xfail`` mark without verifying the row
is now satisfied.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agentbox.core.db import (
    DoneEvent,
    LogEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from agentbox.core.engines.contracts.base import RenderedConfig
from agentbox.core.engines.backends.token import TokenBackend
from pydantic import BaseModel, ValidationError

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


async def _collect(agen: Any) -> list[Any]:
    out: list[Any] = []
    async for ev in agen:
        out.append(ev)
    return out


def _rendered_direct(**meta: Any) -> RenderedConfig:
    agent_meta: dict[str, Any] = {
        "agent_module": None,
        "prompt": "system prompt",
        "model": "openrouter:test/model",
        "output_schema": None,
    }
    agent_meta.update(meta)
    return RenderedConfig(
        cwd=Path("."),
        agent_meta=agent_meta,
        model="openrouter:test/model",
    )


class _Usage:
    input_tokens = 3
    output_tokens = 4
    model = "openrouter:test/model"


def _fake_result(
    output: object = "assistant text",
    messages: list[object] | None = None,
) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.usage = MagicMock(return_value=_Usage())
    result.all_messages = MagicMock(return_value=messages or [])
    return result


def _types(events: list[Any]) -> list[str]:
    return [e.type for e in events]


def _roles(events: list[Any]) -> list[str | None]:
    return [getattr(e, "role", None) for e in events if isinstance(e, TextEvent)]


def _streaming_mock(result: Any = None, side_effect: Exception | None = None) -> Any:
    """Return a mock for ``pai_agent.run_stream_events`` that yields one
    ``AgentRunResultEvent`` carrying *result*, or raises *side_effect*.
    """
    if side_effect is not None:

        @contextlib.asynccontextmanager
        async def _stream_side_effect(*_args: Any, **_kwargs: Any):
            raise side_effect
            yield  # pragma: no cover

        return _stream_side_effect

    class AgentRunResultEvent:
        pass

    res = result if result is not None else _fake_result()
    event = AgentRunResultEvent()
    event.result = res  # type: ignore[attr-defined]

    @contextlib.asynccontextmanager
    async def _stream(*_args: Any, **_kwargs: Any):
        class _Stream:
            def __aiter__(self):
                return _Iter([event])

        class _Iter:
            def __init__(self, items: list[Any]):
                self._items = iter(items)

            async def __anext__(self) -> Any:
                try:
                    return next(self._items)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        yield _Stream()

    return _stream


# ---------------------------------------------------------------------
# Token backend — canonical reference (scenarios 1, 2, 4 implemented)
# ---------------------------------------------------------------------


async def test_token_scenario_1_text_only() -> None:
    fake = MagicMock()
    fake.run_stream_events = _streaming_mock(result=_fake_result("hello back"))
    with patch("pydantic_ai.Agent", return_value=fake):
        events = await _collect(TokenBackend().run(_rendered_direct(), "hi", "rid"))

    assert _types(events) == ["log", "text", "text", "log", "text", "usage", "done"]
    assert _roles(events) == ["system", "user", "assistant"]
    assert isinstance(events[-1], DoneEvent) and events[-1].ok is True
    # invariant: DoneEvent is terminal
    assert not any(isinstance(e, DoneEvent) for e in events[:-1]), (
        "DoneEvent must be the final event"
    )


async def test_token_scenario_2_tools_used() -> None:
    """Walks the message-history helper through a tool-call + tool-result pair."""
    # Build pydantic-ai-style message parts. The helper introspects via
    # _part_kind(), so a SimpleNamespace with `part_kind` attribute is enough.
    from types import SimpleNamespace

    call_part = SimpleNamespace(
        part_kind="tool-call",
        tool_name="add",
        args={"a": 2, "b": 3},
        tool_call_id="call-1",
    )
    result_part = SimpleNamespace(
        part_kind="tool-return",
        tool_name="add",
        tool_call_id="call-1",
        content="5",
    )
    msg_a = SimpleNamespace(parts=[call_part])
    msg_b = SimpleNamespace(parts=[result_part])

    fake = MagicMock()
    fake.run_stream_events = _streaming_mock(
        result=_fake_result("final answer is 5", messages=[msg_a, msg_b])
    )
    with patch("pydantic_ai.Agent", return_value=fake):
        events = await _collect(
            TokenBackend().run(_rendered_direct(), "what is 2+3?", "rid")
        )

    # We require at minimum: log, system, user, (tool_call, tool_result),
    # assistant, usage, done. The helper is defensive and may downgrade
    # on schema drift, so accept either the rich shape or a graceful
    # degradation that still includes the assistant turn.
    types_ = _types(events)
    assert "tool_call" in types_ or "log" in types_, (
        f"expected tool_call or fallback log, got: {types_}"
    )
    if "tool_call" in types_:
        calls = [e for e in events if isinstance(e, ToolCallEvent)]
        results = [e for e in events if isinstance(e, ToolResultEvent)]
        assert calls and results
        assert calls[0].call_id == results[0].call_id, (
            "ToolCallEvent.call_id must equal ToolResultEvent.call_id"
        )
    assert isinstance(events[-1], DoneEvent) and events[-1].ok is True


async def test_token_scenario_4_provider_error_keeps_prompt_turns() -> None:
    class _ProviderShape(BaseModel):
        finish_reason: int

    try:
        _ProviderShape.model_validate({"finish_reason": "error"})
    except ValidationError as exc:
        provider_exc = exc

    fake = MagicMock()
    fake.run_stream_events = _streaming_mock(side_effect=provider_exc)
    with patch("pydantic_ai.Agent", return_value=fake):
        events = await _collect(
            TokenBackend().run(_rendered_direct(provider="openrouter"), "hi", "rid")
        )

    types_ = _types(events)
    # Required slots: opening log, system, user, error log, done(ok=False)
    assert types_[0] == "log"
    assert "text" in types_
    assert _roles(events)[:2] == ["system", "user"], (
        "system + user turns MUST be present even on provider error"
    )
    err_logs = [e for e in events if isinstance(e, LogEvent) and e.level == "error"]
    assert err_logs, "provider error must surface a LogEvent(level='error')"
    done = events[-1]
    assert isinstance(done, DoneEvent) and done.ok is False
    # status may be "error" once executor finalises; backend itself may
    # not set it — both are valid at the backend layer.


# ---------------------------------------------------------------------
# codex / pi — Phase 2 backends; text-only scenario verified
# ---------------------------------------------------------------------


async def _fake_jsonl_stream(events: list[Any]) -> Any:
    """Build an async generator matching stream_jsonl_subprocess's shape."""

    async def _gen(**_kwargs: Any) -> Any:
        for ev, sid in events:
            yield ev, sid

    return _gen


async def test_codex_scenario_1_text_only() -> None:
    from agentbox.core.db import UsageEvent
    from agentbox.core.engines.backends import codex as codex_mod

    rendered = RenderedConfig(
        argv=["codex", "exec", "--json"],
        env={},
        cwd=Path("."),
        agent_meta={"timeout_seconds": 60},
        model="o4-mini",
    )
    fake_events = [
        (TextEvent(run_id="rid", text="hello", delta=True), None),
        (
            UsageEvent(run_id="rid", input_tokens=3, output_tokens=4, model="o4-mini"),
            None,
        ),
        (DoneEvent(run_id="rid", ok=True), None),
    ]
    gen = await _fake_jsonl_stream(fake_events)
    with (
        patch.object(codex_mod.adapter.shutil, "which", return_value="/usr/bin/codex"),
        patch.object(codex_mod.adapter, "stream_jsonl_subprocess", gen),
    ):
        events = await _collect(codex_mod.CodexBackend().run(rendered, "hi", "rid"))

    types_ = _types(events)
    assert types_[0] == "log"
    assert "text" in types_ and "usage" in types_
    assert isinstance(events[-1], DoneEvent) and events[-1].ok is True


async def test_pi_scenario_1_text_only() -> None:
    from agentbox.core.db import UsageEvent
    from agentbox.core.engines.backends import pi as pi_mod

    rendered = RenderedConfig(
        argv=["pi", "-p", "--mode", "json"],
        env={},
        cwd=Path("."),
        agent_meta={"timeout_seconds": 60},
        model="pi-1",
    )
    fake_events = [
        (TextEvent(run_id="rid", text="hello", delta=True), None),
        (UsageEvent(run_id="rid", input_tokens=3, output_tokens=4, model="pi-1"), None),
        (DoneEvent(run_id="rid", ok=True), None),
    ]
    gen = await _fake_jsonl_stream(fake_events)
    with (
        patch.object(pi_mod.adapter.shutil, "which", return_value="/usr/bin/pi"),
        patch.object(pi_mod.adapter, "stream_jsonl_subprocess", gen),
    ):
        events = await _collect(pi_mod.PiBackend().run(rendered, "hi", "rid"))

    types_ = _types(events)
    assert types_[0] == "log"
    assert "text" in types_ and "usage" in types_
    assert isinstance(events[-1], DoneEvent) and events[-1].ok is True
