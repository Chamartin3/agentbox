"""Smoke tests for runners CLI commands."""

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


def _seed_profile(store, profile_id: str = "p1", **kw) -> None:
    from agentbox.core.data import RunnerProfileCreate

    p = RunnerProfileCreate(
        id=profile_id,
        name=kw.get("name", "Test"),
        backend=kw.get("backend", "token"),
        model=kw.get("model", "gpt-4o"),
    )
    store.create_runner_profile(p)


def test_profiles_ls_empty(store_fixture) -> None:
    r = runner.invoke(app, ["runners", "profiles", "ls"])
    assert r.exit_code == 0
    assert "No runner profiles" in r.output


def test_profiles_ls_shows(store_fixture) -> None:
    _seed_profile(store_fixture, "p1")
    r = runner.invoke(app, ["runners", "profiles", "ls"])
    assert r.exit_code == 0
    assert "p1" in r.output


def test_profiles_ls_json(store_fixture) -> None:
    _seed_profile(store_fixture, "p1")
    r = runner.invoke(app, ["runners", "profiles", "ls", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)[0]["id"] == "p1"


def test_profiles_get_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["runners", "profiles", "get", "x"])
    assert r.exit_code != 0


def test_profiles_get_ok(store_fixture) -> None:
    _seed_profile(store_fixture, "p1")
    r = runner.invoke(app, ["runners", "profiles", "get", "p1"])
    assert r.exit_code == 0


def test_profiles_create(store_fixture) -> None:
    r = runner.invoke(
        app,
        [
            "runners",
            "profiles",
            "create",
            "--id",
            "new",
            "--name",
            "N",
            "--backend",
            "token",
        ],
    )
    assert r.exit_code == 0
    assert "new" in r.output


def test_profiles_delete(store_fixture) -> None:
    _seed_profile(store_fixture, "del")
    r = runner.invoke(app, ["runners", "profiles", "delete", "del", "--yes"])
    assert r.exit_code == 0


def test_backends_ls(store_fixture) -> None:
    r = runner.invoke(app, ["runners", "backends", "ls"])
    assert r.exit_code == 0
    assert "Runner Backends" in r.output
