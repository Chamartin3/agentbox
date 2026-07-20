"""Tests for RunRecord and row mappers in core/data/records.py."""

from __future__ import annotations

from datetime import UTC, datetime

from agentbox.core.data.records import RunRecord
from agentbox.core.data import now_iso


class TestNowIso:
    def test_returns_string(self) -> None:
        assert isinstance(now_iso(), str)

    def test_contains_timestamp_format(self) -> None:
        ts = now_iso()
        assert "T" in ts
        assert len(ts) >= 16

    def test_ends_with_zulu_or_offset(self) -> None:
        ts = now_iso()
        assert "+" in ts or ts.endswith("Z")

    def test_is_in_utc_range(self) -> None:
        now_dt = datetime.now(UTC)
        ts = now_iso()
        parsed = datetime.fromisoformat(ts)
        diff = abs((now_dt - parsed).total_seconds())
        assert diff < 5, f"timestamp too far from now: {diff}s"


class TestRunRecord:
    def test_minimal_construction(self) -> None:
        rec = RunRecord(
            id="run-1",
            agent_id="agent-a",
            session_id=None,
            status="running",
            input="hello",
            output=None,
            error=None,
            workdir="/tmp/wd",
            transcript_path=None,
            created_at="2025-01-01T00:00:00Z",
            finished_at=None,
        )
        assert rec.id == "run-1"
        assert rec.status == "running"
        assert rec.input == "hello"

    def test_all_optional_fields_default_none(self) -> None:
        rec = RunRecord(
            id="r",
            agent_id="a",
            session_id=None,
            status="ok",
            input="i",
            output=None,
            error=None,
            workdir=None,
            transcript_path=None,
            created_at="t",
            finished_at=None,
        )
        assert rec.config_digest is None
        assert rec.agent_version_id is None
        assert rec.composition_snapshot is None
        assert rec.rendered_prompt is None
        assert rec.validation_status is None
        assert rec.runner_profile_id is None

    def test_finished_run_has_status_ok(self) -> None:
        rec = RunRecord(
            id="r2",
            agent_id="a",
            session_id="s1",
            status="ok",
            input="in",
            output="out",
            error=None,
            workdir="/wd",
            transcript_path="/wd/t.jsonl",
            created_at="2025-01-01T00:00:00Z",
            finished_at="2025-01-01T00:01:00Z",
            config_digest="abc123",
        )
        assert rec.status == "ok"
        assert rec.output == "out"
        assert rec.finished_at == "2025-01-01T00:01:00Z"


