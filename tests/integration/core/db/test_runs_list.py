"""Tests for the enriched paginated runs list (usage + duration)."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.db import SessionStore


def _seed_run(
    store: SessionStore,
    agent: str,
    status: str,
    model: str | None = "haiku",
    tokens: tuple[int, int] = (10, 20),
) -> str:
    rid = store.create_run(agent, "input text", "/tmp/wd", "/tmp/t.jsonl")
    if model:
        store.record_usage(
            rid,
            {
                "model": model,
                "input_tokens": tokens[0],
                "output_tokens": tokens[1],
                "cost_usd": 0.001,
            },
        )
    if status != "running":
        ok = status == "ok"
        store.finish_run(
            rid, ok=ok, output="out" if ok else None, error=None if ok else "err"
        )
    return rid


def test_list_runs_paged_includes_usage_fields(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    rid = _seed_run(store, "my_agent", "ok", "sonnet-4")

    rows, total = store.list_runs_paged(limit=50)

    assert total == 1
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == rid
    assert row["model"] == "sonnet-4"
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 20
    assert row["cache_read_tokens"] == 0
    assert row["cache_write_tokens"] == 0
    assert row["cost_usd"] == 0.001
    assert isinstance(row["duration_ms"], int)
    assert row["duration_ms"] >= 0


def test_list_runs_paged_no_usage_shows_nulls(tmp_path: Path) -> None:
    """Runs without a usage record should have null usage fields."""
    store = SessionStore(tmp_path / "db.sqlite")
    rid = store.create_run("no_usage_agent", "in", "/wd", "/t.jsonl")
    store.finish_run(rid, ok=True, output="out")

    rows, total = store.list_runs_paged(limit=50)
    assert total == 1
    row = rows[0]
    assert row["id"] == rid
    assert row["model"] is None
    assert row["input_tokens"] is None
    assert row["duration_ms"] is not None


def test_list_runs_paged_duration_for_running(tmp_path: Path) -> None:
    """A running run has finished_at = None -> duration_ms is null."""
    store = SessionStore(tmp_path / "db.sqlite")
    store.create_run("runner", "in", "/wd", "/t.jsonl")

    rows, total = store.list_runs_paged(limit=50)
    assert total == 1
    assert rows[0]["duration_ms"] is None


def test_list_runs_paged_respects_filters(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    _seed_run(store, "a1", "ok", "haiku")
    _seed_run(store, "a2", "error", "sonnet")

    rows, total = store.list_runs_paged(agent_id="a1")
    assert total == 1
    assert rows[0]["agent_id"] == "a1"

    rows, total = store.list_runs_paged(status="error")
    assert total == 1
    assert rows[0]["status"] == "error"

    rows, total = store.list_runs_paged(executor="sonnet")
    assert total == 1
    assert rows[0]["model"] == "sonnet"
