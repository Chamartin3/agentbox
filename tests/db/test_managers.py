"""Tests for the managers catalog + Database access point.

Verifies generic CRUD, custom operations, return-type invariants,
and facade encapsulation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel

from agentbox.core.db import Database
from agentbox.core.db.models.runs.run import Run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def blank_db(tmp_path: Path) -> Database:
    """A Database backed by a temporary SQLite file."""
    db_path = tmp_path / "test.sqlite"
    return Database(db_path)


@pytest.fixture()
def engine_for_schema() -> None:
    """Create the full schema in memory for per-test isolation."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


# ---------------------------------------------------------------------------
# Generic CRUD
# ---------------------------------------------------------------------------


def test_create_returns_model(blank_db: Database) -> None:
    """create() returns a Model instance."""
    run = blank_db.runs.create(
        id="test-1",
        agent_id="agent-a",
        status="running",
        input="hello",
        created_at="2026-01-01T00:00:00",
    )
    assert isinstance(run, Run)


def test_get_returns_none_for_missing(blank_db: Database) -> None:
    """get() returns None when no record matches."""
    assert blank_db.runs.get("nonexistent") is None


def test_get_returns_model(blank_db: Database) -> None:
    """get() returns the matching Model."""
    blank_db.runs.create(
        id="test-2",
        agent_id="agent-a",
        status="running",
        input="hello",
        created_at="2026-01-01T00:00:00",
    )
    run = blank_db.runs.get("test-2")
    assert isinstance(run, Run)
    assert run is not None
    assert run.id == "test-2"
    assert run.agent_id == "agent-a"


def test_find_returns_filtered_list(blank_db: Database) -> None:
    """find() returns models matching the given filters."""
    blank_db.runs.create(
        id="r1", agent_id="a", status="running", input="in1", created_at="now"
    )
    blank_db.runs.create(
        id="r2", agent_id="a", status="ok", input="in2", created_at="now"
    )
    blank_db.runs.create(
        id="r3", agent_id="b", status="running", input="in3", created_at="now"
    )

    agent_a_runs = blank_db.runs.find(agent_id="a")
    assert len(agent_a_runs) == 2

    running_a_runs = blank_db.runs.find(agent_id="a", status="ok")
    assert len(running_a_runs) == 1
    assert running_a_runs[0].id == "r2"


def test_all_returns_everything(blank_db: Database) -> None:
    """all() returns every record in the table."""
    blank_db.runs.create(
        id="r1", agent_id="a", status="running", input="i", created_at="now"
    )
    blank_db.runs.create(
        id="r2", agent_id="b", status="ok", input="j", created_at="now"
    )
    assert len(blank_db.runs.all()) == 2


def test_update_persists_changes(blank_db: Database) -> None:
    """update() writes model changes back to the DB."""
    r = blank_db.runs.create(
        id="upd-1", agent_id="a", status="running", input="hello", created_at="now"
    )
    r.status = "ok"
    blank_db.runs.update(r)
    reloaded = blank_db.runs.get("upd-1")
    assert reloaded is not None
    assert reloaded.status == "ok"


def test_delete_removes_record(blank_db: Database) -> None:
    """delete() removes the record from the DB."""
    r = blank_db.runs.create(
        id="del-1", agent_id="a", status="running", input="x", created_at="now"
    )
    blank_db.runs.delete(r)
    assert blank_db.runs.get("del-1") is None


# ---------------------------------------------------------------------------
# Custom operation
# ---------------------------------------------------------------------------


def test_run_manager_finish(blank_db: Database) -> None:
    """RunManager.finish updates status/output/error/finished_at."""
    blank_db.runs.create(
        id="fin-1", agent_id="a", status="running", input="test", created_at="now"
    )
    blank_db.runs.finish("fin-1", status="ok", output="done", finished_at="2026-01-01T01:00:00")
    r = blank_db.runs.get("fin-1")
    assert r is not None
    assert r.status == "ok"
    assert r.output == "done"
    assert r.finished_at == "2026-01-01T01:00:00"


def test_runner_profile_get_default(blank_db: Database) -> None:
    """RunnerProfileManager.get_default returns the system default profile."""
    blank_db.runner_profiles.create(
        id="prof-1",
        name="Default",
        backend="token",
        is_enabled=1,
        is_system_default=1,
        created_at="now",
        updated_at="now",
    )
    default = blank_db.runner_profiles.get_default()
    assert default is not None
    assert default.id == "prof-1"


# ---------------------------------------------------------------------------
# Return-type invariants
# ---------------------------------------------------------------------------


def test_generic_reads_return_models(blank_db: Database) -> None:
    """Every generic read returns Model / list[Model] / None — never a dict."""
    blank_db.runs.create(
        id="type-1", agent_id="a", status="ok", input="hi", created_at="now"
    )

    obj = blank_db.runs.get("type-1")
    assert obj is not None
    assert isinstance(obj, Run)

    all_ = blank_db.runs.all()
    assert isinstance(all_, list)
    assert all(isinstance(r, Run) for r in all_)

    found = blank_db.runs.find(agent_id="a")
    assert isinstance(found, list)
    assert all(isinstance(r, Run) for r in found)


# ---------------------------------------------------------------------------
# Encapsulation invariants
# ---------------------------------------------------------------------------


def test_facade_exports_database_and_models(blank_db: Database) -> None:
    """The facade exports Database + Models but not engine/Entity/Manager."""
    import agentbox.core.db as db_pkg

    public = set(getattr(db_pkg, "__all__", []))
    assert "Database" in public
    assert "Run" in public
    # Internal machinery not in __all__
    assert "Entity" not in public
    assert "Engine" not in public
    assert "Manager" not in public


def test_create_missing_required_field_raises(blank_db: Database) -> None:
    """create() with a missing NOT NULL column raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        blank_db.runs.create(
            id="no-input",
            agent_id="a",
            status="running",
            # missing required "input" and "created_at" columns
        )
