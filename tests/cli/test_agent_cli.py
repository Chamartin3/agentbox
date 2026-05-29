"""Smoke tests for agent CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from agentbox.cli import app

runner = CliRunner()


def _clear_deps_caches() -> None:
    from agentbox.cli._deps import (
        get_executor,
        get_loader,
        get_mcp_registry,
        get_settings,
        get_store,
    )

    for fn in (get_settings, get_store, get_loader, get_executor, get_mcp_registry):
        fn.cache_clear()


@pytest.fixture
def store_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest = tmp_path / "agentbox.toml"
    manifest.write_text("# test manifest\n")
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    _clear_deps_caches()
    from agentbox.cli._deps import get_store as _get_store

    store = _get_store()
    yield store
    _clear_deps_caches()


def _seed_agent(store, agent_id: str = "t1") -> str:
    from agentbox.core.data import AgentDef

    agent_def = AgentDef(
        id=agent_id, description="Test", runner={"kind": "token", "model": "gpt-4o"}
    )
    store.create_agent(
        agent_id=agent_id,
        config_json=agent_def.model_dump(
            mode="python", exclude_none=True, warnings=False
        ),
        prompt_content="# Test",
        author="t",
        changelog="s",
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )
    return agent_id


def test_agents_ls_empty(store_fixture) -> None:
    r = runner.invoke(app, ["agents", "ls"])
    assert r.exit_code == 0
    assert "No agents" in r.output


def test_agents_ls_shows(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "ls", "--json"])
    assert r.exit_code == 0
    assert len(json.loads(r.output)) == 1


def test_agents_show_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["agents", "show", "x"])
    assert r.exit_code != 0


def test_agents_show_ok(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "show", "t1"])
    assert r.exit_code == 0


def test_agents_delete(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "delete", "t1", "--yes"])
    assert r.exit_code == 0
    assert "deleted" in r.output


def test_agents_grants_ls(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "grants", "ls", "t1"])
    assert r.exit_code == 0


def test_agents_tools_ls(store_fixture) -> None:
    r = runner.invoke(app, ["agents", "tools", "ls"])
    assert r.exit_code == 0


def test_agents_versions_ls(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "versions", "ls", "t1"])
    assert r.exit_code == 0


def test_agents_validation_get(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "validation", "get", "t1"])
    assert r.exit_code == 0


def test_agents_runner_profile_get(store_fixture) -> None:
    _seed_agent(store_fixture, "t1")
    r = runner.invoke(app, ["agents", "runner-profile", "t1", "--get"])
    assert r.exit_code == 0
