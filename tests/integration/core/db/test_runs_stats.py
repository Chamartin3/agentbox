"""Tests for the stats-for-filters aggregation (dashboard endpoint).

Exercises ``RunManager.stats_for_filters``. Seeding goes through
``ExecutionService`` (self-wired to the test's sqlite); queries read the
manager on that same cached ``Database``.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.service.execution import ExecutionService


def _svc() -> ExecutionService:
    return ExecutionService()


def _seed(
    agent: str,
    status: str,
    model: str = "haiku",
) -> str:
    svc = _svc()
    rid = svc.create_run(agent, "in", "/wd", "/t.jsonl")
    svc.record_usage(
        rid,
        {"model": model, "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01},
    )
    if status != "running":
        svc.finish_run(
            rid,
            ok=(status == "ok"),
            output="out" if status == "ok" else None,
            error=None if status == "ok" else "err",
        )
    return rid


def test_stats_totals(tmp_path: Path) -> None:
    _seed("agent_a", "ok", "haiku")
    _seed("agent_a", "error", "haiku")
    _seed("agent_b", "ok", "sonnet")

    stats = _svc()._db.runs.stats_for_filters()
    t = stats["totals"]
    assert t["runs"] == 3
    assert t["input_tokens"] == 300
    assert t["output_tokens"] == 150
    assert t["cost_usd"] == 0.03
    assert t["avg_duration_ms"] >= 0


def test_stats_by_agent(tmp_path: Path) -> None:
    _seed("agent_a", "ok", "haiku")
    _seed("agent_b", "ok", "sonnet")
    _seed("agent_b", "error", "sonnet")

    stats = _svc()._db.runs.stats_for_filters()
    by_agent = {r["agent_id"]: r for r in stats["by_agent"]}
    assert by_agent["agent_b"]["runs"] == 2
    assert by_agent["agent_a"]["runs"] == 1


def test_stats_by_model(tmp_path: Path) -> None:
    _seed("a1", "ok", "haiku")
    _seed("a2", "ok", "sonnet")
    _seed("a3", "ok", "sonnet")

    stats = _svc()._db.runs.stats_for_filters()
    by_model = {r["model"]: r for r in stats["by_model"]}
    assert by_model["sonnet"]["runs"] == 2
    assert by_model["haiku"]["runs"] == 1


def test_stats_by_status(tmp_path: Path) -> None:
    _seed("a1", "ok")
    _seed("a2", "error")
    _seed("a3", "ok")

    stats = _svc()._db.runs.stats_for_filters()
    by_status = {r["status"]: r for r in stats["by_status"]}
    assert by_status["ok"]["runs"] == 2
    assert by_status["error"]["runs"] == 1


def test_stats_timeseries(tmp_path: Path) -> None:
    _seed("a1", "ok", "haiku")

    stats = _svc()._db.runs.stats_for_filters()
    assert len(stats["timeseries"]) >= 1
    bucket = stats["timeseries"][0]
    assert "bucket" in bucket
    assert bucket["runs"] >= 1


def test_stats_respects_agent_filter(tmp_path: Path) -> None:
    _seed("agent_a", "ok", "haiku")
    _seed("agent_b", "ok", "sonnet")

    stats = _svc()._db.runs.stats_for_filters(agent_id="agent_a")
    assert stats["totals"]["runs"] == 1
    assert stats["totals"]["input_tokens"] == 100


def test_stats_respects_status_filter(tmp_path: Path) -> None:
    _seed("a1", "ok")
    _seed("a2", "error")

    stats = _svc()._db.runs.stats_for_filters(status="ok")
    assert stats["totals"]["runs"] == 1
    assert len(stats["by_status"]) == 1
    assert stats["by_status"][0]["status"] == "ok"


def test_stats_unknown_model_bucketing(tmp_path: Path) -> None:
    """Runs without usage records get 'unknown' model."""
    svc = _svc()
    rid = svc.create_run("a1", "in", "/wd", "/t.jsonl")
    svc.finish_run(rid, ok=True, output="out")

    stats = svc._db.runs.stats_for_filters()
    by_model = {r["model"]: r for r in stats["by_model"]}
    assert "unknown" in by_model
