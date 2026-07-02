"""Tests for activity-summary aggregation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentbox.core.data import now_iso
from agentbox.core.db.database import Database


def _seed(db: Database, agent: str, status: str, model: str = "haiku") -> str:
    rid = uuid.uuid4().hex
    db.runs.create(
        id=rid,
        agent_id=agent,
        status="running",
        input="in",
        workdir="/tmp/wd",
        transcript_path="/tmp/t.jsonl",
        created_at=now_iso(),
    )
    db.usage.record(
        rid,
        {"model": model, "input_tokens": 10, "output_tokens": 20, "cost_usd": 0.001},
    )
    if status != "running":
        db.runs.finish_full(
            run_id=rid,
            ok=(status == "ok"),
            output=None,
            error=None if status == "ok" else "boom",
        )
    return rid


def test_activity_summary_basic(tmp_path: Path) -> None:
    db = Database(tmp_path / "agentbox.sqlite")
    _seed(db, "fill_job_post", "ok", "haiku")
    _seed(db, "fill_job_post", "error", "haiku")
    _seed(db, "extract_keywords", "ok", "sonnet")
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")

    s = db.runs.activity_summary(since)
    t = s["totals"]
    assert t["runs"] == 3
    assert t["successes"] == 2
    assert t["failures"] == 1
    assert t["failure_rate_pct"] == 33.3
    assert t["input_tokens"] == 30
    assert t["output_tokens"] == 60
    assert round(t["cost_usd"], 4) == 0.003
    actions = {row["action_name"]: row for row in s["by_action"]}
    assert actions["fill_job_post"]["total"] == 2
    assert actions["fill_job_post"]["failures"] == 1
    assert actions["extract_keywords"]["total"] == 1
    models = {row["reported_model"]: row for row in s["by_reported_model"]}
    assert models["haiku"]["total"] == 2
    assert models["sonnet"]["total"] == 1


def test_activity_summary_agent_filter(tmp_path: Path) -> None:
    db = Database(tmp_path / "agentbox.sqlite")
    _seed(db, "fill_job_post", "ok")
    _seed(db, "extract_keywords", "ok")
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    s = db.runs.activity_summary(since, agent="fill_job_post")
    assert s["totals"]["runs"] == 1


def test_list_runs_rich(tmp_path: Path) -> None:
    db = Database(tmp_path / "agentbox.sqlite")
    rid = _seed(db, "fill_job_post", "ok", "haiku")
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    rows = db.runs.list_runs_rich(since)
    assert len(rows) == 1
    assert rows[0]["id"] == rid
    assert rows[0]["reported_model"] == "haiku"
    assert rows[0]["input_tokens"] == 10
