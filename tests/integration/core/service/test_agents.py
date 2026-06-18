"""Tests for ``core.services.agents`` — the shared resolver behind REST + MCP.

The point of the service layer is that REST routes and MCP tools cannot
drift: both call ``resolve_agent`` / ``list_all_agents``, so anything
the DB knows about appears on both surfaces.

There is no manifest fallback any more — the DB is the only source.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from agentbox.core.db import AgentDef
from agentbox.core.db import SessionStore
from agentbox.core.service.agents import list_all_agents, resolve_agent


def _make_agent_def(agent_id: str, description: str = "") -> AgentDef:
    return AgentDef.model_validate({"id": agent_id, "description": description})


def _seed_db_agent(store: SessionStore, agent_id: str) -> None:
    """Insert a single ``agent_versions`` row + active pointer."""
    agent = _make_agent_def(agent_id, description=f"db-{agent_id}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
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


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


def test_resolve_agent_returns_db_agent(store: SessionStore) -> None:
    _seed_db_agent(store, "stage.draft_fixer")

    agent = resolve_agent("stage.draft_fixer", store=store)

    assert agent is not None
    assert agent.id == "stage.draft_fixer"
    assert agent.description == "db-stage.draft_fixer"


def test_resolve_agent_returns_none_when_unknown(store: SessionStore) -> None:
    assert resolve_agent("missing", store=store) is None


def test_resolve_agent_ignores_loader_kwarg(store: SessionStore) -> None:
    """``loader`` is accepted for backward compatibility but ignored."""
    _seed_db_agent(store, "in_db")

    agent = resolve_agent("in_db", store=store, loader=object())

    assert agent is not None
    assert agent.id == "in_db"

    assert resolve_agent("not_in_db", store=store, loader=object()) is None


def test_list_all_agents_returns_db_agents_only(store: SessionStore) -> None:
    _seed_db_agent(store, "db_one")
    _seed_db_agent(store, "db_two")

    listed = list_all_agents(store=store)
    by_id = {a.id: a for a in listed}

    assert set(by_id) == {"db_one", "db_two"}
    assert by_id["db_one"].description == "db-db_one"


def test_list_all_agents_skips_invalid_snapshots(
    store: SessionStore, caplog: pytest.LogCaptureFixture
) -> None:
    _seed_db_agent(store, "good")
    # An incomplete row (no config payload) must be skipped silently.
    store.create_version(
        agent_id="broken",
        source_path="",
        source_format="db_only",
        content_snapshot="",
        prompt_snapshot="",
        content_hash="x",
        config_json=None,
        prompt_content="",
        source="manifest",
    )

    listed = list_all_agents(store=store)

    assert [a.id for a in listed] == ["good"]
