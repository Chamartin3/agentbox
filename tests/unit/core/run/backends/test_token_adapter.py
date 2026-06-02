from __future__ import annotations

import contextlib
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agentbox.core.data import TextEvent
from agentbox.core.engines.backends.base import RenderedConfig
from agentbox.core.engines.backends.token import TokenBackend
from pydantic import BaseModel, ValidationError


async def _collect(agen):
    events = []
    async for ev in agen:
        events.append(ev)
    return events


def _direct_rendered(**meta: object) -> RenderedConfig:
    agent_meta = {
        "agent_module": None,
        "prompt": "system prompt",
        "model": "openrouter:test/model",
        "output_schema": None,
    }
    agent_meta.update(meta)
    return RenderedConfig(
        cwd=Path("."), files={}, agent_meta=agent_meta, model="openrouter:test/model"
    )


class _Usage:
    input_tokens = 3
    output_tokens = 4
    model = "openrouter:test/model"


def _fake_result(
    output: object = "assistant text", messages: list[object] | None = None
):
    result = MagicMock()
    result.output = output
    result.usage = MagicMock(return_value=_Usage())
    result.all_messages = MagicMock(return_value=messages or [])
    return result


def _streaming_mock(result: object | None = None, side_effect: Exception | None = None):
    """Build a *run_stream_events* mock compatible with ``async with`` +
    ``async for`` that yields a single ``AgentRunResultEvent``.
    """
    if side_effect is not None:

        @contextlib.asynccontextmanager
        async def _stream_side_effect(*_args, **_kwargs):
            raise side_effect
            yield  # pragma: no cover

        return _stream_side_effect

    class AgentRunResultEvent:
        pass

    res = result if result is not None else _fake_result()
    result_event = AgentRunResultEvent()
    result_event.result = res  # type: ignore[attr-defined]

    @contextlib.asynccontextmanager
    async def _stream(*_args, **_kwargs):
        class _Stream:
            def __aiter__(self):
                return _StreamIterator([result_event])

        class _StreamIterator:
            def __init__(self, items):
                self._items = iter(items)

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        yield _Stream()

    return _stream


async def test_direct_mode_emits_system_user_assistant_on_success() -> None:
    fake_agent = MagicMock()
    fake_agent.run_stream_events = _streaming_mock(_fake_result("assistant text"))

    with patch("pydantic_ai.Agent", return_value=fake_agent):
        events = await _collect(TokenBackend().run(_direct_rendered(), "hello", "rid"))

    assert [e.type for e in events] == [
        "log",
        "text",
        "text",
        "log",
        "text",
        "usage",
        "done",
    ]
    assert [getattr(e, "role", None) for e in events if e.type == "text"] == [
        "system",
        "user",
        "assistant",
    ]
    assert events[-1].ok is True


async def test_direct_mode_surfaces_openrouter_finish_reason_error() -> None:
    class _ProviderShape(BaseModel):
        finish_reason: int

    try:
        _ProviderShape.model_validate({"finish_reason": "error"})
    except ValidationError as exc:
        provider_exc = exc

    fake_agent = MagicMock()
    fake_agent.run_stream_events = _streaming_mock(
        side_effect=provider_exc,
    )

    rendered = _direct_rendered(provider="openrouter")
    with patch("pydantic_ai.Agent", return_value=fake_agent):
        events = await _collect(TokenBackend().run(rendered, "hello", "rid"))

    text_roles = [getattr(e, "role", None) for e in events if e.type == "text"]
    assert text_roles == ["system", "user"]
    error_logs = [e for e in events if e.type == "log" and e.level == "error"]
    assert error_logs and "finish_reason" in error_logs[0].message
    assert events[-1].type == "done"
    assert events[-1].ok is False
    assert events[-1].status == "error"


async def test_direct_mode_emits_tool_call_and_result_from_message_history() -> None:
    messages = [
        SimpleNamespace(
            parts=[
                SimpleNamespace(
                    part_kind="tool-call",
                    tool_name="add_numbers",
                    args={"a": 2, "b": 3},
                    tool_call_id="call-1",
                )
            ]
        ),
        SimpleNamespace(
            parts=[
                SimpleNamespace(
                    part_kind="tool-return",
                    tool_name="add_numbers",
                    content="5",
                    tool_call_id="call-1",
                )
            ]
        ),
    ]
    fake_agent = MagicMock()
    fake_agent.run_stream_events = _streaming_mock(_fake_result("5", messages))

    with patch("pydantic_ai.Agent", return_value=fake_agent):
        events = await _collect(TokenBackend().run(_direct_rendered(), "2+3", "rid"))

    tool_call = next(e for e in events if e.type == "tool_call")
    tool_result = next(e for e in events if e.type == "tool_result")
    assert tool_call.tool == "add_numbers"
    assert tool_call.arguments == {"a": 2, "b": 3}
    assert tool_call.call_id == "call-1"
    assert tool_result.tool == "add_numbers"
    assert tool_result.call_id == "call-1"
    assert tool_result.result_excerpt == "5"


async def test_full_agent_mode_emits_system_user_assistant() -> None:
    class RequestModel(BaseModel):
        value: str

    class FakeAgent:
        INPUT_TYPE = RequestModel

        def __init__(self, **kwargs):
            self.model = "fake-model"
            self._message_history = []

        def render_prompts(self, request: RequestModel) -> tuple[str, str]:
            return "full system", f"full user {request.value}"

        def run_sync(self, request: RequestModel) -> dict[str, str]:
            return {"answer": request.value}

    rendered = RenderedConfig(
        cwd=Path("."),
        files={},
        agent_meta={
            "agent_module": "fake.module:FakeAgent",
            "prompt": "fallback system",
            "model": "openai:gpt-4o",
            "output_schema": None,
        },
        model="openai:gpt-4o",
    )

    with patch.object(TokenBackend, "_import_agent", return_value=FakeAgent):
        events = await _collect(TokenBackend().run(rendered, '{"value":"ok"}', "rid"))

    assert [e.type for e in events] == ["log", "text", "text", "text", "usage", "done"]
    text_events = [e for e in events if e.type == "text"]
    assert [(e.role, e.text) for e in text_events[:2]] == [
        ("system", "full system"),
        ("user", "full user ok"),
    ]
    assert text_events[2].role == "assistant"


async def test_missing_api_key_still_emits_done_error() -> None:
    rendered = _direct_rendered(
        provider="openrouter", api_key_env="AGENTBOX_MISSING_KEY"
    )

    events = await _collect(TokenBackend().run(rendered, "hello", "rid"))

    assert [e.type for e in events] == ["log", "done"]
    assert events[-1].ok is False
    assert "AGENTBOX_MISSING_KEY" in (events[-1].error or "")


def test_role_filter_in_session_does_not_include_system_or_user_text_in_output() -> (
    None
):
    """System/user TextEvents are transcribed + broadcast but not added to
    the run output — only assistant turns contribute to ``output_text``.
    Logic lives on ``RunStreamSession.emit`` post-Plan 16."""
    from agentbox.core.run.streaming.session import RunStreamSession

    tf = StringIO()
    broadcaster = SimpleNamespace(publish=lambda ev: None)
    session = RunStreamSession(
        run_id="rid",
        broadcaster=broadcaster,
        transcript_path=Path("/dev/null"),
    )
    session._transcript_fh = tf

    session.emit(TextEvent(run_id="rid", role="system", text="sys"))
    session.emit(TextEvent(run_id="rid", role="user", text="usr"))
    session.emit(TextEvent(run_id="rid", role="assistant", text="out"))

    assert session.output_text == ["out"]
    assert '"role":"system"' in tf.getvalue()
    assert '"role":"user"' in tf.getvalue()


def test_transcript_conversation_source_preserves_prompt_roles_and_tool_payloads() -> (
    None
):
    from agentbox.core.run.history.sources.transcript import (
        _events_to_conversation_view,
    )

    view = _events_to_conversation_view(
        events=[
            {"type": "text", "run_id": "rid", "role": "system", "text": "sys"},
            {"type": "text", "run_id": "rid", "role": "user", "text": "usr"},
            {
                "type": "tool_call",
                "run_id": "rid",
                "tool": "add_numbers",
                "arguments": {"a": 2, "b": 3},
            },
            {
                "type": "tool_result",
                "run_id": "rid",
                "tool": "add_numbers",
                "result_excerpt": "5",
            },
        ],
        run_id="rid",
        source_format="pydantic-ai-history",
        source_uri=None,
        include_bodies=True,
    )

    assert [turn.role for turn in view.turns] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert view.turns[2].content[0].tool_name == "add_numbers"
    assert view.turns[3].content[0].body == "5"
