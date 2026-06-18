"""Tests for the stats-for-filters aggregation (dashboard endpoint)."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db import SessionStore


def _seed(
    store: SessionStore,
    agent: str,
    status: str,
    model: str = "haiku",
) -> str:
    rid = store.create_run(agent, "in", "/wd", "/t.jsonl")
    store.record_usage(
        rid,
        {"model": model, "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01},
    )
    if status != "running":
        store.finish_run(
            rid,
            ok=(status == "ok"),
            output="out" if status == "ok" else None,
            error=None if status == "ok" else "err",
        )
    return rid


@pytest.mark.unit
def test_stats_totals(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "agent_a", "ok", "haiku")
    _seed(store, "agent_a", "error", "haiku")
    _seed(store, "agent_b", "ok", "sonnet")

    stats = store.stats_for_filters()
    t = stats["totals"]
    assert t["runs"] == 3
    assert t["input_tokens"] == 300
    assert t["output_tokens"] == 150
    assert t["cost_usd"] == 0.03
    assert t["avg_duration_ms"] >= 0


@pytest.mark.unit
def test_stats_by_agent(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "agent_a", "ok", "haiku")
    _seed(store, "agent_b", "ok", "sonnet")
    _seed(store, "agent_b", "error", "sonnet")

    stats = store.stats_for_filters()
    by_agent = {r["agent_id"]: r for r in stats["by_agent"]}
    assert by_agent["agent_b"]["runs"] == 2
    assert by_agent["agent_a"]["runs"] == 1


@pytest.mark.unit
def test_stats_by_model(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "a1", "ok", "haiku")
    _seed(store, "a2", "ok", "sonnet")
    _seed(store, "a3", "ok", "sonnet")

    stats = store.stats_for_filters()
    by_model = {r["model"]: r for r in stats["by_model"]}
    assert by_model["sonnet"]["runs"] == 2
    assert by_model["haiku"]["runs"] == 1


@pytest.mark.unit
def test_stats_by_status(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "a1", "ok")
    _seed(store, "a2", "error")
    _seed(store, "a3", "ok")

    stats = store.stats_for_filters()
    by_status = {r["status"]: r for r in stats["by_status"]}
    assert by_status["ok"]["runs"] == 2
    assert by_status["error"]["runs"] == 1


@pytest.mark.unit
def test_stats_timeseries(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "a1", "ok", "haiku")

    stats = store.stats_for_filters()
    assert len(stats["timeseries"]) >= 1
    bucket = stats["timeseries"][0]
    assert "bucket" in bucket
    assert bucket["runs"] >= 1


@pytest.mark.unit
def test_stats_respects_agent_filter(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "agent_a", "ok", "haiku")
    _seed(store, "agent_b", "ok", "sonnet")

    stats = store.stats_for_filters(agent_id="agent_a")
    assert stats["totals"]["runs"] == 1
    assert stats["totals"]["input_tokens"] == 100


@pytest.mark.unit
def test_stats_respects_status_filter(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed(store, "a1", "ok")
    _seed(store, "a2", "error")

    stats = store.stats_for_filters(status="ok")
    assert stats["totals"]["runs"] == 1
    assert len(stats["by_status"]) == 1
    assert stats["by_status"][0]["status"] == "ok"


@pytest.mark.unit
def test_stats_unknown_model_bucketing(tmp_path: Path) -> None:
    """Runs without usage records get 'unknown' model."""
    store = SessionStore(tmp_path / "db.sqlite")
    rid = store.create_run("a1", "in", "/wd", "/t.jsonl")
    store.finish_run(rid, ok=True, output="out")

    stats = store.stats_for_filters()
    by_model = {r["model"]: r for r in stats["by_model"]}
    assert "unknown" in by_model
