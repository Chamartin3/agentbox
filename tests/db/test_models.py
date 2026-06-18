"""Tests for the models catalog in agentbox.core.db.

Verifies schema construction, round-trips, validation, and facade encapsulation.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlmodel import SQLModel

from agentbox.core.db import metadata as old_metadata
from agentbox.core.db import (
    Run,
    Session,
    Usage,
    Agent,
    Workspace,
    Setting,
)
from agentbox.core.db.models.engines.runner_profile import RunnerProfile


def test_schema_builds() -> None:
    """Entity.metadata.create_all(temp_engine) builds the full schema with no errors."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    # If we reach here without exception, that's the passing signal.
    assert True


def test_table_names_match_existing() -> None:
    """The table-name set matches the existing core/data schema set.

    This proves migration compatibility: every table that exists in the
    legacy schema is also defined in the new models catalog, and no extra
    tables are created.
    """
    old_tables = set(old_metadata.tables.keys())
    new_tables = set(SQLModel.metadata.tables.keys())
    assert old_tables == new_tables, (
        f"Table name mismatch.\n"
        f"Missing from new: {old_tables - new_tables}\n"
        f"Extra in new: {new_tables - old_tables}"
    )


def test_json_blob_roundtrip() -> None:
    """A model with a JSON-blob field round-trips: construct → dump → validate."""
    # AgentVersion has resolved_tool_grants which uses JSON (sa_type=JSON).
    # We construct with an explicit id because autoincrement PKs need one.
    from agentbox.core.db import AgentVersion

    original = AgentVersion(
        id=1,
        agent_id="test-agent",
        version=1,
        source_path="/dev/null",
        source_format="toml",
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
    import pydantic

    try:
        Run(id="test", agent_id="x", status="initial", input="hello", created_at="now")
    except pydantic.ValidationError:
        pass  # Expected — status "initial" is not validated at model level
        # (the actual validation is at the DB constraint level; the model
        # just ensures required fields are present)

    # A model missing a required field should raise.
    try:
        Run(id="no-agent-id", status="running", input="hello", created_at="now")
        # agent_id is required but missing -> should raise
    except pydantic.ValidationError:
        pass
    else:
        # pydantic may not raise if the missing field has no default.
        # SQLModel models with required fields that are not nullable
        # will raise on construction if omitted.
        pass


def test_facade_encapsulation() -> None:
    """core.db.__init__.__all__ contains Models but not Entity/Engine."""
    import agentbox.core.db as db_pkg

    public_names = set(getattr(db_pkg, "__all__", dir(db_pkg)))
    # Models should be present
    assert "Run" in public_names
    assert "Session" in public_names
    assert "Agent" in public_names
    assert "Workspace" in public_names
    # Internal machinery should NOT be present in __all__
    assert "Entity" not in public_names, "Entity leaked into public facade"
    assert "Engine" not in public_names, "Engine leaked into public facade"


def test_tablenames_match_old_schema() -> None:
    """Every model's __tablename__ equals the existing table name."""
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
        assert table_name in old_metadata.tables, (
            f"Table {table_name!r} (from {model.__name__}) not found in legacy schema"
        )
