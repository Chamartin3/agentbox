"""Tests for ``RunStreamSession`` — the central event capture object."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentbox.core.data import (
    DoneEvent,
    LogEvent,
    TextEvent,
    UsageEvent,
    ValidationEvent,
)
from agentbox.core.run.executor import RunBroadcaster
from agentbox.core.run.streaming.session import (
    CaptureSession,
    DoneAlreadyEmittedError,
    RunStreamSession,
)


def _read_transcript(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_emit_writes_transcript_publishes_and_accumulates(tmp_path: Path) -> None:
    """One emit() call hits all three sinks atomically."""
    broadcaster = RunBroadcaster()
    queue = broadcaster.subscribe()
    transcript = tmp_path / "t.jsonl"

    with RunStreamSession(
        run_id="r1", broadcaster=broadcaster, transcript_path=transcript
    ) as s:
        s.emit(TextEvent(run_id="r1", text="hello", role="assistant"))

    # Transcript persisted.
    rows = _read_transcript(transcript)
    assert len(rows) == 1
    assert rows[0]["type"] == "text"
    assert rows[0]["text"] == "hello"

    # Broadcaster received it.
    ev = queue.get_nowait()
    assert isinstance(ev, TextEvent)

    # Output accumulator captured assistant text.
    assert s.output_text == ["hello"]


def test_delta_text_is_not_accumulated(tmp_path: Path) -> None:
    """Delta text events are UI-only; they don't become run output."""
    with RunStreamSession(
        run_id="r1",
        broadcaster=RunBroadcaster(),
        transcript_path=tmp_path / "t.jsonl",
    ) as s:
        s.emit(TextEvent(run_id="r1", text="chunk", role="assistant", delta=True))
        s.emit(TextEvent(run_id="r1", text="final", role="assistant"))

    assert s.output_text == ["final"]


def test_user_text_is_not_accumulated(tmp_path: Path) -> None:
    """Only assistant-role text becomes run output."""
    with RunStreamSession(
        run_id="r1",
        broadcaster=RunBroadcaster(),
        transcript_path=tmp_path / "t.jsonl",
    ) as s:
        s.emit(TextEvent(run_id="r1", text="prompt", role="user"))

    assert s.output_text == []


def test_done_must_be_last(tmp_path: Path) -> None:
    """Any emit() after DoneEvent raises — UI clients treat done as terminal."""
    with RunStreamSession(
        run_id="r1",
        broadcaster=RunBroadcaster(),
        transcript_path=tmp_path / "t.jsonl",
    ) as s:
        s.emit_done(ok=True)
        with pytest.raises(DoneAlreadyEmittedError):
            s.emit(LogEvent(run_id="r1", level="info", message="too late"))


def test_validation_before_done_is_allowed(tmp_path: Path) -> None:
    """The whole point of the invariant — validation must precede done."""
    with RunStreamSession(
        run_id="r1",
        broadcaster=RunBroadcaster(),
        transcript_path=tmp_path / "t.jsonl",
    ) as s:
        s.emit_validation(ok=True, mode="strict", engine="both", error=None)
        s.emit_done(ok=True)

    rows = _read_transcript(tmp_path / "t.jsonl")
    assert [r["type"] for r in rows] == ["validation", "done"]


def test_observer_fires_per_event(tmp_path: Path) -> None:
    """Observer hooks let the executor wire UsageEvent → store.record_usage."""
    seen: list[str] = []
    with RunStreamSession(
        run_id="r1",
        broadcaster=RunBroadcaster(),
        transcript_path=tmp_path / "t.jsonl",
    ) as s:
        s.add_observer(lambda ev: seen.append(ev.type))
        s.emit(LogEvent(run_id="r1", level="info", message="hi"))
        s.emit(UsageEvent(run_id="r1", input_tokens=10, output_tokens=20))

    assert seen == ["log", "usage"]


def test_observer_exceptions_are_swallowed(tmp_path: Path) -> None:
    """A broken observer must not stop events from reaching transcript/WS."""
    queue = RunBroadcaster()
    qsub = queue.subscribe()
    with RunStreamSession(
        run_id="r1", broadcaster=queue, transcript_path=tmp_path / "t.jsonl"
    ) as s:
        s.add_observer(lambda ev: 1 / 0)
        s.emit(LogEvent(run_id="r1", level="info", message="still works"))

    # Event still made it to transcript and broadcaster despite observer crash.
    assert _read_transcript(tmp_path / "t.jsonl")[0]["message"] == "still works"
    assert qsub.get_nowait().message == "still works"


def test_validation_mode_engine_are_clamped(tmp_path: Path) -> None:
    """Unknown mode/engine strings get clamped — Pydantic discriminators
    reject anything else and we don't want a bad runner crashing the stream."""
    with RunStreamSession(
        run_id="r1",
        broadcaster=RunBroadcaster(),
        transcript_path=tmp_path / "t.jsonl",
    ) as s:
        s.emit_validation(ok=False, mode="garbage", engine="garbage", error="x")

    row = _read_transcript(tmp_path / "t.jsonl")[0]
    assert row["mode"] == "strict"
    assert row["engine"] == "none"


def test_capture_session_records_in_memory() -> None:
    """``CaptureSession`` is the test double — same invariants, no I/O."""
    with CaptureSession() as s:
        s.emit(LogEvent(run_id=s.run_id, level="info", message="x"))
        s.emit_validation(ok=True, mode="strict", engine="both", error=None)
        s.emit_done(ok=True)

    assert [type(e) for e in s.captured] == [LogEvent, ValidationEvent, DoneEvent]
    with pytest.raises(DoneAlreadyEmittedError):
        s.emit(LogEvent(run_id=s.run_id, level="info", message="too late"))


def test_transcript_is_closed_on_exit(tmp_path: Path) -> None:
    """Context manager exit closes the file handle, even on exception."""
    transcript = tmp_path / "t.jsonl"
    s = RunStreamSession(
        run_id="r1", broadcaster=RunBroadcaster(), transcript_path=transcript
    )
    with s:
        s.emit(LogEvent(run_id="r1", level="info", message="x"))
        assert s._transcript_fh is not None
    assert s._transcript_fh is None
