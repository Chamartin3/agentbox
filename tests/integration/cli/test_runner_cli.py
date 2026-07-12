"""Smoke tests for runners CLI commands — profiles, backends, providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentbox.cli import app
from agentbox.cli.shared import (
    get_executor,
    get_mcp_registry,
)
from agentbox.cli.shared.deps import (
    get_engine_service,
    get_settings,
    get_db as _get_store,
)
from agentbox.core.data import AgentDef, RunnerProfileCreate, RunnerSpec
from agentbox.core.service.engines import EngineService
from agentbox.core.service.agents import AgentService

runner = CliRunner()


def _clear_deps_caches() -> None:
    for fn in (get_settings, _get_store, get_executor, get_mcp_registry, get_engine_service):
        fn.cache_clear()


@pytest.fixture
def store_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    _clear_deps_caches()
    store = _get_store()
    yield store
    _clear_deps_caches()


def _seed_agent(store, agent_id: str = "test-agent") -> None:
    agent_def = AgentDef(
        id=agent_id,
        description="Test agent",
        runner=RunnerSpec(kind="token", model="gpt-4o"),
    )
    AgentService().create_agent(
        agent_id=agent_id,
        config_json=agent_def.model_dump(
            mode="python", exclude_none=True, warnings=False
        ),
        prompt_content="# Test prompt\n",
        author="test",
        changelog="seed",
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )


def _seed_profile(store, profile_id: str = "prof-1", **kw) -> None:
    profile = RunnerProfileCreate(
        id=profile_id,
        name=kw.get("name", "Test Profile"),
        backend=kw.get("backend", "token"),
        provider=kw.get("provider", "openai"),
        model=kw.get("model", "gpt-4o"),
    )
    EngineService().create_profile(profile)


# ---------------------------------------------------------------------------
# engine profile ls
# ---------------------------------------------------------------------------


def test_profiles_ls_empty(store_fixture) -> None:
    result = runner.invoke(app, ["engine", "profile", "ls"])
    assert result.exit_code == 0
    assert "No runner profiles found" in result.output


def test_profiles_ls_shows_profile(store_fixture) -> None:
    _seed_profile(store_fixture)
    result = runner.invoke(app, ["engine", "profile", "ls"])
    assert result.exit_code == 0
    assert "prof-1" in result.output
    assert "Test Profile" in result.output


def test_profiles_ls_json(store_fixture) -> None:
    _seed_profile(store_fixture)
    result = runner.invoke(app, ["engine", "profile", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "prof-1"


def test_profiles_ls_filter_backend(store_fixture) -> None:
    _seed_profile(store_fixture, "prof-tok", backend="token")
    result = runner.invoke(app, ["engine", "profile", "ls", "--backend", "token"])
    assert result.exit_code == 0
    assert "prof-tok" in result.output


# ---------------------------------------------------------------------------
# engine profile show
# ---------------------------------------------------------------------------


def test_profiles_get_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["engine", "profile", "show", "no-such"])
    assert result.exit_code != 0


def test_profiles_get_existing(store_fixture) -> None:
    _seed_profile(store_fixture)
    result = runner.invoke(app, ["engine", "profile", "show", "prof-1"])
    assert result.exit_code == 0
    assert "prof-1" in result.output


# ---------------------------------------------------------------------------
# engine profile new
# ---------------------------------------------------------------------------


def test_profiles_create(store_fixture) -> None:
    result = runner.invoke(
        app,
        [
            "engine",
            "profile",
            "new",
            "--id",
            "new-prof",
            "--name",
            "New Profile",
            "--backend",
            "token",
        ],
    )
    assert result.exit_code == 0
    assert "new-prof" in result.output


def test_profiles_create_duplicate(store_fixture) -> None:
    _seed_profile(store_fixture, "dup-prof")
    result = runner.invoke(
        app,
        [
            "engine",
            "profile",
            "new",
            "--id",
            "dup-prof",
            "--name",
            "Duplicate",
            "--backend",
            "token",
        ],
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# engine profile bind
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# engine profile rm
# ---------------------------------------------------------------------------


def test_profiles_delete(store_fixture) -> None:
    _seed_profile(store_fixture, "to-delete")
    result = runner.invoke(app, ["engine", "profile", "rm", "to-delete", "--yes"])
    assert result.exit_code == 0


def test_profiles_delete_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["engine", "profile", "rm", "no-such", "--yes"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# engine backend ls
# ---------------------------------------------------------------------------


def test_backends_ls(store_fixture) -> None:
    result = runner.invoke(app, ["engine", "backend", "ls"])
    assert result.exit_code == 0
    assert "Runner Backends" in result.output


def test_backends_ls_json(store_fixture) -> None:
    result = runner.invoke(app, ["engine", "backend", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
    assert "id" in parsed[0]
