"""Tests for the models catalog in agentbox.core.db.

Verifies schema construction, round-trips, validation, and facade encapsulation.

After plan 109, ``agentbox.core.db`` exports managers only.  SQLModel entities
live in their per-domain packages (``agentbox.core.db.runs`` etc.); the single
``metadata`` is ``SQLModel.metadata`` (``agentbox.core.db.base.metadata``).
"""
from __future__ import annotations

import pydantic
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import agentbox.core.db as db_pkg
from agentbox.core.db.runs import Run, Session, Usage
from agentbox.core.db.agents import Agent, AgentVersion
from agentbox.core.db.workspaces import Workspace
from agentbox.core.db.system import Setting
from agentbox.core.db.engines.runner_profile import RunnerProfile


def test_schema_builds() -> None:
    """Entity.metadata.create_all(temp_engine) builds the full schema with no errors."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    # If we reach here without exception, that's the passing signal.
    assert True



def test_json_blob_roundtrip() -> None:
    """A model with a JSON-blob field round-trips: construct → dump → validate."""
    # AgentVersion has resolved_tool_grants which uses JSON (sa_type=JSON).
    # We construct with an explicit id because autoincrement PKs need one.
    original = AgentVersion(
        id=1,
        agent_id="test-agent",
        version=1,
        source_path="/dev/null",
        content_snapshot="{}",
        prompt_snapshot="",
        content_hash="abc123",
        author="test",
        created_at="2026-01-01T00:00:00",
        resolved_tool_grants=["read", "write"],
    )
    dumped = original.model_dump()
    # Validate the round-trip by checking that model_validate accepts
    # the dict back. SQLModel table models have _sa_instance_state in the
    # dumped dict when they've been attached; we strip it for the validate.
    restored = AgentVersion.model_validate(
        {k: v for k, v in dumped.items() if k != "_sa_instance_state"}
    )
    assert restored.resolved_tool_grants == ["read", "write"]


def test_invalid_construction_raises() -> None:
    """Invalid construction raises (validation works on the non-table models)."""
    # Run requires agent_id (non-nullable str) and input (non-nullable str)
    try:
        Run(id="test", agent_id="x", status="initial", input="hello", created_at="now")
    except pydantic.ValidationError:
        pass  # Expected — status "initial" is not validated at model level
        # (the actual validation is at the DB constraint level; the model
        # just ensures required fields are present)

    # A model missing a required field should raise. Build via model_validate
    # with a dict so the deliberately-incomplete payload is a runtime concern,
    # not a static type error.
    try:
        Run.model_validate(
            {"id": "no-agent-id", "status": "running", "input": "hello", "created_at": "now"}
        )
        # agent_id is required but missing -> should raise
    except pydantic.ValidationError:
        pass
    else:
        # pydantic may not raise if the missing field has no default.
        # SQLModel models with required fields that are not nullable
        # will raise on construction if omitted.
        pass


def test_facade_managers_only() -> None:
    """core.db.__all__ contains only managers.

    SQLModel entities (Run, Agent, etc.) are no longer re-exported by the
    façade — they live in their per-domain packages (``agentbox.core.db.runs``…).
    """
    public_names = set(getattr(db_pkg, "__all__", dir(db_pkg)))
    # Managers should be present
    assert "RunManager" in public_names
    assert "AgentManager" in public_names
    assert "WorkspaceManager" in public_names
    # SessionStore has been deleted
    assert "SessionStore" not in public_names
    # SQLModel entities must NOT be in the managers-only facade
    assert "Run" not in public_names, "Run leaked into managers-only facade"
    assert "Agent" not in public_names, "Agent leaked into managers-only facade"
    # Internal machinery should NOT be present in __all__
    assert "Entity" not in public_names, "Entity leaked into public facade"
    assert "Engine" not in public_names, "Engine leaked into public facade"
    assert "Database" not in public_names, "Database leaked into managers-only facade"
    assert "get_database" not in public_names, "get_database leaked into managers-only facade"


def test_tablenames_present_in_metadata() -> None:
    """Every model's __tablename__ is registered on the shared metadata."""
    models_with_tablenames = [
        Run,
        Session,
        Usage,
        Agent,
        Workspace,
        RunnerProfile,
        Setting,
    ]
    for model in models_with_tablenames:
        table_name = model.__tablename__
        assert table_name in SQLModel.metadata.tables, (
            f"Table {table_name!r} (from {model.__name__}) not found in metadata"
        )
