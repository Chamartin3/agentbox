"""Tests for ``core.services.agents`` — the shared resolver behind REST + MCP.

The point of the service layer is that REST routes and MCP tools cannot
drift: both call ``resolve_agent`` / ``list_all_agents``, so anything
the DB knows about appears on both surfaces. These tests pin the DB-first
behavior (the bug that motivated the refactor was MCP looking up agents
via the manifest loader only, returning ``not_found`` for DB-only agents
the REST API listed fine).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import pytest
from agentbox.core.data.manifest import AgentDef, ProjectManifest
from agentbox.core.data.store import SessionStore
from agentbox.core.services.agents import list_all_agents, resolve_agent


def _make_agent_def(agent_id: str, description: str = "") -> AgentDef:
    return AgentDef.model_validate({"id": agent_id, "description": description})


def _seed_db_agent(store: SessionStore, agent_id: str) -> None:
    """Insert a single ``agent_versions`` row + active pointer."""
    agent = _make_agent_def(agent_id, description=f"db-{agent_id}")
    # Mirror ``core/versioning/drift._build_config_json``: the AgentDef
    # has an enum-default quirk that triggers a pydantic UserWarning on
    # serialization; production swallows it the same way.
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


@dataclass
class _StubLoader:
    """Fake ``DefinitionLoader`` used to control the manifest side."""

    agents: list[AgentDef]

    def load(self) -> ProjectManifest:
        m = ProjectManifest()
        m.agents = list(self.agents)
        return m

    def get(self, agent_id: str) -> AgentDef | None:
        for a in self.agents:
            if a.id == agent_id:
                return a
        return None


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


def test_resolve_agent_returns_db_only_agent(store: SessionStore) -> None:
    """The bug: MCP ``get_agent`` used loader.get only and missed DB-only agents."""
    _seed_db_agent(store, "stage.draft_fixer")
    loader = _StubLoader(agents=[])  # manifest has nothing

    agent = resolve_agent("stage.draft_fixer", store=store, loader=loader)

    assert agent is not None
    assert agent.id == "stage.draft_fixer"
    assert agent.description == "db-stage.draft_fixer"


def test_resolve_agent_falls_back_to_loader(store: SessionStore) -> None:
    loader = _StubLoader(agents=[_make_agent_def("manifest_only", "from-toml")])

    agent = resolve_agent("manifest_only", store=store, loader=loader)

    assert agent is not None
    assert agent.description == "from-toml"


def test_resolve_agent_returns_none_when_unknown(store: SessionStore) -> None:
    loader = _StubLoader(agents=[])

    assert resolve_agent("missing", store=store, loader=loader) is None


def test_resolve_agent_db_wins_over_manifest(store: SessionStore) -> None:
    """When both have the id, the DB snapshot is authoritative."""
    _seed_db_agent(store, "both")
    loader = _StubLoader(agents=[_make_agent_def("both", "from-manifest")])

    agent = resolve_agent("both", store=store, loader=loader)

    assert agent is not None
    assert agent.description == "db-both"


def test_list_all_agents_unions_db_and_manifest(store: SessionStore) -> None:
    _seed_db_agent(store, "db_one")
    _seed_db_agent(store, "shared")
    loader = _StubLoader(
        agents=[
            _make_agent_def("shared", "from-manifest"),
            _make_agent_def("manifest_only"),
        ]
    )

    listed = list_all_agents(store=store, loader=loader)
    by_id = {a.id: a for a in listed}

    assert set(by_id) == {"db_one", "shared", "manifest_only"}
    # DB wins on overlap (description matches the seeded DB snapshot).
    assert by_id["shared"].description == "db-shared"


def test_list_all_agents_survives_manifest_failure(
    store: SessionStore, caplog: pytest.LogCaptureFixture
) -> None:
    _seed_db_agent(store, "db_one")

    class _BrokenLoader:
        def load(self) -> ProjectManifest:
            raise RuntimeError("manifest unreadable")

        def get(self, agent_id: str) -> AgentDef | None:
            return None

    listed = list_all_agents(store=store, loader=_BrokenLoader())  # type: ignore[arg-type]
    assert [a.id for a in listed] == ["db_one"]
