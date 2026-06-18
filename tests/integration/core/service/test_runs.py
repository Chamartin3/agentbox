"""Tests for the runs service — dispatch, lifecycle, listing, and detail."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentbox.core.db import SessionStore
from agentbox.core.execution.orchestrate.executor import NoBackendAvailable
from agentbox.core.service.execution import runs as runs_service
from agentbox.core.service.execution.runs import (
    AgentNotFound,
    InvalidRunInput,
    RunNotFound,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeExecutor:
    def __init__(self, run_id: str = "new-run-id") -> None:
        self._run_id = run_id
        self.calls: list[dict[str, Any]] = []
        self.cancelled: list[str] = []

    async def execute(self, agent, input_, **kwargs):
        self.calls.append({"agent_id": agent.id, "input": input_, **kwargs})
        return self._run_id

    async def cancel_run(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True


def _seed_agent(store: SessionStore, agent_id: str = "alpha") -> None:
    import warnings as _w

    from agentbox.core.db import AgentDef

    agent = AgentDef.model_validate({"id": agent_id, "description": "x"})
    with _w.catch_warnings():
        _w.simplefilter("ignore", category=UserWarning)
        config_json = agent.model_dump_json()
    row = store.create_version(
        agent_id=agent_id,
        source_path="",
        source_format="db_only",
        content_snapshot=config_json,
        prompt_snapshot="",
        content_hash="x",
        config_json=config_json,
        prompt_content="",
        source="manifest",
    )
    store.activate_version(agent_id, row["id"])


def _seed_run(
    store: SessionStore,
    agent_id: str = "alpha",
    workdir: str = "/tmp/wd",
) -> str:
    return store.create_run(
        agent_id=agent_id,
        input_="hello",
        workdir=workdir,
        transcript_path="/tmp/wd/transcript.jsonl",
    )


def _seed_run_with_usage(
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


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


# ---------------------------------------------------------------------------
# create_run
# ---------------------------------------------------------------------------


async def test_create_run_raises_when_agent_unknown(store: SessionStore) -> None:
    with pytest.raises(AgentNotFound):
        await runs_service.create_run(
            "missing", store=store, executor=_FakeExecutor(), variables={}
        )


async def test_create_run_raises_invalid_when_no_input_or_variables(
    store: SessionStore,
) -> None:
    _seed_agent(store)
    with pytest.raises(InvalidRunInput):
        await runs_service.create_run(
            "alpha", store=store, executor=_FakeExecutor()
        )


async def test_create_run_dispatches_legacy_input(store: SessionStore) -> None:
    _seed_agent(store)
    ex = _FakeExecutor()
    result = await runs_service.create_run(
        "alpha", store=store, executor=ex, input_="hi"
    )
    assert result == {"run_id": "new-run-id", "agent": "alpha"}
    assert ex.calls[0]["input"] == "hi"
    assert "variables" not in ex.calls[0]


async def test_create_run_dispatches_with_variables(store: SessionStore) -> None:
    _seed_agent(store)
    ex = _FakeExecutor()
    await runs_service.create_run(
        "alpha", store=store, executor=ex, variables={"k": "v"}
    )
    assert ex.calls[0]["variables"] == {"k": "v"}
    assert ex.calls[0]["input"] == ""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_complete_run_raises_when_unknown(store: SessionStore) -> None:
    with pytest.raises(RunNotFound):
        runs_service.complete_run(
            "no-such-run",
            store=store,
            ok=True,
            output=None,
            error=None,
            usage=None,
        )


def test_complete_run_marks_terminal_and_fires_callback(
    store: SessionStore,
) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    calls: list[tuple] = []

    def cb(agent, refreshed, s):
        calls.append((agent.id if agent else None, refreshed.id, s))

    result = runs_service.complete_run(
        run_id,
        store=store,
        ok=True,
        output="result",
        error=None,
        usage=None,
        schedule_webhook_cb=cb,
    )
    assert result["ok"] is True
    rec = store.get_run(run_id)
    assert rec.status == "ok"
    assert calls and calls[0][0] == "alpha"


def test_post_outcome_records_status(store: SessionStore) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    result = runs_service.post_outcome(
        run_id, store=store, status="ok", error_kind=None, errors=None
    )
    assert result["ok"] is True
    assert result["run_id"] == run_id


def test_post_outcome_raises_when_unknown(store: SessionStore) -> None:
    with pytest.raises(RunNotFound):
        runs_service.post_outcome("missing", store=store, status="ok")


async def test_cancel_run_idempotent_on_terminal(store: SessionStore) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    store.finish_run(run_id, ok=True, output="done")
    ex = _FakeExecutor()
    result = await runs_service.cancel_run(run_id, store=store, executor=ex)
    assert result["cancelled"] is False
    assert ex.cancelled == []


async def test_cancel_run_calls_executor_when_running(store: SessionStore) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    ex = _FakeExecutor()
    result = await runs_service.cancel_run(run_id, store=store, executor=ex)
    assert result["cancelled"] is True
    assert ex.cancelled == [run_id]


async def test_cancel_run_raises_when_unknown(store: SessionStore) -> None:
    with pytest.raises(RunNotFound):
        await runs_service.cancel_run(
            "missing", store=store, executor=_FakeExecutor()
        )


# ---------------------------------------------------------------------------
# Listing / detail
# ---------------------------------------------------------------------------


def test_list_runs_returns_raw_list_when_unfiltered(store: SessionStore) -> None:
    _seed_agent(store)
    _seed_run(store)
    result = runs_service.list_runs(store=store)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["agent_version"] is None


def test_list_runs_returns_envelope_when_paginated(store: SessionStore) -> None:
    _seed_agent(store)
    _seed_run(store)
    result = runs_service.list_runs(store=store, paginated=True)
    assert isinstance(result, dict)
    assert set(result) == {"items", "total", "offset", "limit", "has_more"}
    assert result["total"] == 1


def test_get_run_detail_raises_when_unknown(store: SessionStore) -> None:
    with pytest.raises(RunNotFound):
        runs_service.get_run_detail("missing", store=store)


def test_get_run_detail_shape(store: SessionStore) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    detail = runs_service.get_run_detail(run_id, store=store)
    assert set(detail) == {"run", "usage"}
    assert detail["run"]["id"] == run_id
    assert detail["run"]["backend"] is None


def test_run_facets_includes_known_statuses(store: SessionStore) -> None:
    facets = runs_service.run_facets(store=store)
    assert "running" in facets["statuses"]
    assert "ok" in facets["statuses"]


# ---------------------------------------------------------------------------
# Paginated listing with usage fields
# ---------------------------------------------------------------------------


def test_list_runs_paged_includes_usage_fields(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "db.sqlite")
    rid = _seed_run_with_usage(store, "my_agent", "ok", "sonnet-4")

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
    _seed_run_with_usage(store, "a1", "ok", "haiku")
    _seed_run_with_usage(store, "a2", "error", "sonnet")

    rows, total = store.list_runs_paged(agent_id="a1")
    assert total == 1
    assert rows[0]["agent_id"] == "a1"

    rows, total = store.list_runs_paged(status="error")
    assert total == 1
    assert rows[0]["status"] == "error"

    rows, total = store.list_runs_paged(executor="sonnet")
    assert total == 1
    assert rows[0]["model"] == "sonnet"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_list_comments_raises_when_unknown(store: SessionStore) -> None:
    with pytest.raises(RunNotFound):
        runs_service.list_comments("missing", store=store)


def test_add_and_list_comment(store: SessionStore) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    runs_service.add_comment(run_id, store=store, author="me", body="hi")
    listed = runs_service.list_comments(run_id, store=store)
    assert listed["run_id"] == run_id
    assert len(listed["comments"]) == 1
    assert listed["comments"][0]["body"] == "hi"


# ---------------------------------------------------------------------------
# no_backend_detail
# ---------------------------------------------------------------------------


def test_no_backend_detail_lists_attempted_and_loaded() -> None:
    exc = NoBackendAvailable(agent_id="alpha", attempted=["bogus_one"])
    detail = runs_service.no_backend_detail(exc)
    assert "alpha" in detail
    assert "bogus_one" in detail
    assert "Registered backends" in detail
