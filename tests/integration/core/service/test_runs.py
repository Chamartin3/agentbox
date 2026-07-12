"""Tests for the runs service — dispatch, lifecycle, listing, and detail."""

from __future__ import annotations

import warnings as _w
from pathlib import Path
from typing import Any, cast

import pytest

from agentbox.core.data import AgentDef
from agentbox.core.config import load_settings
from agentbox.core.db.database import Database
from agentbox.core.execution.orchestrate.executor import NoBackendAvailable, RunExecutor
import agentbox.core.service.execution as runs_service
from agentbox.core.service.execution import ExecutionService
from agentbox.core.service.agents import AgentService
from agentbox.core.service.execution import (
    AgentNotFound,
    InvalidRunInput,
    RunNotFound,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeExecutor:
    def __init__(self, db=None, settings=None, run_id: str = "new-run-id") -> None:
        self._run_id = run_id
        self.calls: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        # create_run composes the prompt via build_prompt(db, settings) before
        # dispatch, so the stub carries a real db/settings.
        self.db = db
        self.settings = settings

    async def execute(self, composed, **kwargs):
        self.calls.append(
            {"agent_id": composed.agent.id, "input": composed.input_, **kwargs}
        )
        return self._run_id

    async def cancel_run(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True


def _seed_agent(store: Database, agent_id: str = "alpha") -> None:
    agent = AgentDef.model_validate({"id": agent_id, "description": "x"})
    with _w.catch_warnings():
        _w.simplefilter("ignore", category=UserWarning)
        config_json = agent.model_dump_json()
    row = AgentService().create_version(
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
    AgentService().activate_version(agent_id, row["id"])


def _svc() -> ExecutionService:
    """ExecutionService self-wires to settings.db_path == the test's sqlite."""
    return ExecutionService()


def _seed_run(
    store: Database,
    agent_id: str = "alpha",
    workdir: str = "/tmp/wd",
) -> str:
    return _svc().create_run(
        agent_id=agent_id,
        input_="hello",
        workdir=workdir,
        transcript_path="/tmp/wd/transcript.jsonl",
    )


def _seed_run_with_usage(
    store: Database,
    agent: str,
    status: str,
    model: str | None = "haiku",
    tokens: tuple[int, int] = (10, 20),
) -> str:
    svc = _svc()
    rid = svc.create_run(agent, "input text", "/tmp/wd", "/tmp/t.jsonl")
    if model:
        svc.record_usage(
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
        svc.finish_run(
            rid, ok=ok, output="out" if ok else None, error=None if ok else "err"
        )
    return rid


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


# ---------------------------------------------------------------------------
# create_run
# ---------------------------------------------------------------------------


async def test_create_run_raises_when_agent_unknown(store: Database) -> None:
    with pytest.raises(AgentNotFound):
        await ExecutionService().dispatch_run(
            "missing", agent_defs=store.agent_defs, agent_meta=store.agent_meta, executor=cast(RunExecutor, _FakeExecutor()), variables={}
        )


async def test_create_run_raises_invalid_when_no_input_or_variables(
    store: Database,
) -> None:
    _seed_agent(store)
    with pytest.raises(InvalidRunInput):
        await ExecutionService().dispatch_run(
            "alpha", agent_defs=store.agent_defs, agent_meta=store.agent_meta, executor=cast(RunExecutor, _FakeExecutor())
        )


async def test_create_run_dispatches_legacy_input(store: Database) -> None:
    _seed_agent(store)
    ex = _FakeExecutor(store, load_settings())
    result = await ExecutionService().dispatch_run(
        "alpha", agent_defs=store.agent_defs, agent_meta=store.agent_meta, executor=cast(RunExecutor, ex), input_="hi"
    )
    assert result == {"run_id": "new-run-id", "agent": "alpha"}
    assert ex.calls[0]["input"] == "hi"
    assert ex.calls[0]["variables"] is None


async def test_create_run_dispatches_with_variables(store: Database) -> None:
    _seed_agent(store)
    ex = _FakeExecutor(store, load_settings())
    await ExecutionService().dispatch_run(
        "alpha", agent_defs=store.agent_defs, agent_meta=store.agent_meta, executor=cast(RunExecutor, ex), variables={"k": "v"}
    )
    assert ex.calls[0]["variables"] == {"k": "v"}
    assert ex.calls[0]["input"] == ""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_complete_run_raises_when_unknown(store: Database) -> None:
    with pytest.raises(RunNotFound):
        ExecutionService().complete_run(
            "no-such-run",
            agent_defs=store.agent_defs,
            ok=True,
            output=None,
            error=None,
            usage=None,
        )


def test_complete_run_marks_terminal_and_fires_callback(
    store: Database,
) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    calls: list[tuple] = []

    def cb(agent, refreshed):
        calls.append((agent.id if agent else None, refreshed.id))

    result = ExecutionService().complete_run(
        run_id,
        agent_defs=store.agent_defs,
        ok=True,
        output="result",
        error=None,
        usage=None,
        schedule_webhook_cb=cb,
    )
    assert result["ok"] is True
    rec = _svc().get_run(run_id)
    assert rec is not None
    assert rec.status == "ok"
    assert calls and calls[0][0] == "alpha"


def test_post_outcome_records_status(store: Database) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    result = ExecutionService().post_outcome(
        run_id, status="ok", error_kind=None, errors=None
    )
    assert result["ok"] is True
    assert result["run_id"] == run_id


def test_post_outcome_raises_when_unknown(store: Database) -> None:
    with pytest.raises(RunNotFound):
        ExecutionService().post_outcome("missing", status="ok")


async def test_cancel_run_idempotent_on_terminal(store: Database) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    _svc().finish_run(run_id, ok=True, output="done")
    ex = _FakeExecutor()
    result = await ExecutionService().cancel_run(run_id, executor=cast(RunExecutor, ex))
    assert result["cancelled"] is False
    assert ex.cancelled == []


async def test_cancel_run_calls_executor_when_running(store: Database) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    ex = _FakeExecutor()
    result = await ExecutionService().cancel_run(run_id, executor=cast(RunExecutor, ex))
    assert result["cancelled"] is True
    assert ex.cancelled == [run_id]


async def test_cancel_run_raises_when_unknown(store: Database) -> None:
    with pytest.raises(RunNotFound):
        await ExecutionService().cancel_run(
            "missing", executor=cast(RunExecutor, _FakeExecutor())
        )


# ---------------------------------------------------------------------------
# Listing / detail
# ---------------------------------------------------------------------------


def test_list_runs_returns_raw_list_when_unfiltered(store: Database) -> None:
    _seed_agent(store)
    _seed_run(store)
    result = ExecutionService().list_runs_enriched(agent_versions=store.agent_versions)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["agent_version"] is None


def test_list_runs_returns_envelope_when_paginated(store: Database) -> None:
    _seed_agent(store)
    _seed_run(store)
    result = ExecutionService().list_runs_enriched(agent_versions=store.agent_versions, paginated=True)
    assert isinstance(result, dict)
    assert set(result) == {"items", "total", "offset", "limit", "has_more"}
    assert result["total"] == 1


def test_get_run_detail_raises_when_unknown(store: Database) -> None:
    with pytest.raises(RunNotFound):
        ExecutionService().get_run_detail("missing", agent_versions=store.agent_versions)


def test_get_run_detail_shape(store: Database) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    detail = ExecutionService().get_run_detail(run_id, agent_versions=store.agent_versions)
    assert set(detail) == {"run", "usage"}
    assert detail["run"]["id"] == run_id
    assert detail["run"]["backend"] is None


def test_run_facets_includes_known_statuses(store: Database) -> None:
    facets = ExecutionService().run_facets()
    assert "running" in facets["statuses"]
    assert "ok" in facets["statuses"]


# ---------------------------------------------------------------------------
# Paginated listing with usage fields
# ---------------------------------------------------------------------------


def test_list_runs_paged_includes_usage_fields(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.sqlite")
    rid = _seed_run_with_usage(store, "my_agent", "ok", "sonnet-4")

    rows, total = _svc()._db.runs.list_runs_paged(limit=50)

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
    rid = _svc().create_run("no_usage_agent", "in", "/wd", "/t.jsonl")
    _svc().finish_run(rid, ok=True, output="out")

    rows, total = _svc()._db.runs.list_runs_paged(limit=50)
    assert total == 1
    row = rows[0]
    assert row["id"] == rid
    assert row["model"] is None
    assert row["input_tokens"] is None
    assert row["duration_ms"] is not None


def test_list_runs_paged_duration_for_running(tmp_path: Path) -> None:
    """A running run has finished_at = None -> duration_ms is null."""
    _svc().create_run("runner", "in", "/wd", "/t.jsonl")

    rows, total = _svc()._db.runs.list_runs_paged(limit=50)
    assert total == 1
    assert rows[0]["duration_ms"] is None


def test_list_runs_paged_respects_filters(tmp_path: Path) -> None:
    store = Database(tmp_path / "agentbox.sqlite")
    _seed_run_with_usage(store, "a1", "ok", "haiku")
    _seed_run_with_usage(store, "a2", "error", "sonnet")

    rows, total = _svc()._db.runs.list_runs_paged(agent_id="a1")
    assert total == 1
    assert rows[0]["agent_id"] == "a1"

    rows, total = _svc()._db.runs.list_runs_paged(status="error")
    assert total == 1
    assert rows[0]["status"] == "error"

    rows, total = _svc()._db.runs.list_runs_paged(executor="sonnet")
    assert total == 1
    assert rows[0]["model"] == "sonnet"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_list_comments_raises_when_unknown(store: Database) -> None:
    with pytest.raises(RunNotFound):
        ExecutionService().list_comments("missing")


def test_add_and_list_comment(store: Database) -> None:
    _seed_agent(store)
    run_id = _seed_run(store)
    ExecutionService().add_comment(run_id, author="me", body="hi")
    listed = ExecutionService().list_comments(run_id)
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
