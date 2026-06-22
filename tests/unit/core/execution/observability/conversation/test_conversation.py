"""Tests for conversation observability — _events_to_conversation_view."""

from __future__ import annotations

from agentbox.core.execution.observability.conversation.transcript import (
    _events_to_conversation_view,
)
from agentbox.core.execution.observability.conversation.types import (
    ConversationView,
)


def _ev(type_: str, **kwargs: object) -> dict:
    return {"type": type_, "ts": "2024-01-01T00:00:00", **kwargs}


# ---------------------------------------------------------------------------
# Text → turn mapping
# ---------------------------------------------------------------------------


class TestTextToTurn:
    def test_assistant_text(self) -> None:
        events = [_ev("text", text="Hello", role="assistant")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert len(view.turns) >= 1

    def test_user_text(self) -> None:
        events = [_ev("text", text="Hi", role="user")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert view.turns[0].role.value == "user"

    def test_missing_role_defaults(self) -> None:
        events = [_ev("text", text="x")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert view.turns[0].role.value == "assistant"


# ---------------------------------------------------------------------------
# thinking events
# ---------------------------------------------------------------------------


class TestThinkingEvents:
    def test_thinking_becomes_content_part(self) -> None:
        events = [_ev("thinking", text="hmm...")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert len(view.turns) == 1
        assert view.turns[0].content[0].type == "thinking"


# ---------------------------------------------------------------------------
# log events
# ---------------------------------------------------------------------------


class TestLogEvents:
    def test_log_does_not_crash(self) -> None:
        events = [_ev("log", text="some log")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert isinstance(view, ConversationView)


# ---------------------------------------------------------------------------
# usage accumulation
# ---------------------------------------------------------------------------


class TestUsageAccumulation:
    def test_usage_accumulates_tokens(self) -> None:
        events = [
            _ev("usage", input_tokens=10, output_tokens=5),
            _ev("usage", input_tokens=20, output_tokens=8),
        ]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert view.totals.input_tokens == 30
        assert view.totals.output_tokens == 13

    def test_usage_with_cache_tokens(self) -> None:
        events = [_ev("usage", input_tokens=10, output_tokens=5,
                        cache_read_tokens=3, cache_write_tokens=2)]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert view.totals.cache_read_tokens == 3
        assert view.totals.cache_write_tokens == 2


# ---------------------------------------------------------------------------
# done event
# ---------------------------------------------------------------------------


class TestDoneEvent:
    def test_done_event_does_not_crash(self) -> None:
        events = [_ev("done", status="ok")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert isinstance(view, ConversationView)


# ---------------------------------------------------------------------------
# empty events
# ---------------------------------------------------------------------------


class TestEmpty:
    def test_empty_events_returns_empty_view(self) -> None:
        view = _events_to_conversation_view(
            events=[], run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert len(view.turns) == 0
        assert view.totals.input_tokens == 0

    def test_unknown_event_type_skipped(self) -> None:
        events = [_ev("unknown_type", foo="bar")]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl", source_uri=None,
        )
        assert len(view.turns) == 0


# ---------------------------------------------------------------------------
# pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_offset_and_limit(self) -> None:
        events = [{"type": "text", "role": "assistant", "text": f"msg{i}"}
                  for i in range(10)]
        view = _events_to_conversation_view(
            events=events, run_id="r1", source_format="jsonl",
            source_uri=None, offset=2, limit=3,
        )
        assert 1 <= len(view.turns) <= 5
