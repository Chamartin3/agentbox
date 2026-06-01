"""RunEvent discriminated union — every variant round-trips through JSON."""

from __future__ import annotations

import json

import pytest
from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)
from pydantic import TypeAdapter, ValidationError

RUN_ID = "r1"
_ADAPTER: TypeAdapter[RunEvent] = TypeAdapter(RunEvent)


@pytest.mark.parametrize(
    "event",
    [
        ToolCallEvent(run_id=RUN_ID, tool="bash", arguments={"cmd": "ls"}),
        ToolResultEvent(run_id=RUN_ID, tool="bash", ok=True, result_excerpt="a\nb"),
        TextEvent(run_id=RUN_ID, text="hi"),
        UsageEvent(run_id=RUN_ID, input_tokens=10, output_tokens=2, model="haiku"),
        LogEvent(run_id=RUN_ID, level="warn", message="oops"),
        DoneEvent(run_id=RUN_ID, ok=True),
        DoneEvent(run_id=RUN_ID, ok=False, status="timeout", error="took too long"),
    ],
    ids=lambda e: e.type,
)
def test_event_roundtrips_through_json(event) -> None:  # type: ignore[no-untyped-def]
    raw = event.model_dump_json()
    parsed = _ADAPTER.validate_json(raw)
    assert parsed.type == event.type
    assert parsed.run_id == event.run_id


def test_done_event_defaults() -> None:
    ev = DoneEvent(run_id=RUN_ID, ok=True)
    assert ev.type == "done"
    assert ev.exit_code is None
    assert ev.status is None
    assert ev.ts is not None


def test_text_event_default_role_is_assistant() -> None:
    ev = TextEvent(run_id=RUN_ID, text="hi")
    assert ev.role == "assistant"


def test_unknown_type_rejected() -> None:
    payload = json.dumps({"type": "bogus", "run_id": RUN_ID})
    with pytest.raises(ValidationError):
        _ADAPTER.validate_json(payload)
