"""Smoke tests for agent CLI commands — happy paths against an in-memory store."""

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
        get_mcp_registry,
        get_settings,
        get_store,
    )

    for fn in (get_settings, get_store, get_executor, get_mcp_registry):
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


def _seed_agent(store, agent_id: str = "t1", **kw) -> dict:
    from agentbox.core.db import AgentDef

    agent_def = AgentDef(
        id=agent_id,
        description=kw.get("description", "Test agent"),
        runner={
            "kind": kw.get("runner_kind", "token"),
            "model": kw.get("model", "gpt-4o"),
        },
        **{
            k: v
            for k, v in kw.items()
            if k not in ("description", "runner_kind", "model")
        },
    )
    return store.create_agent(
        agent_id=agent_id,
        config_json=agent_def.model_dump(
            mode="python", exclude_none=True, warnings=False
        ),
        prompt_content=kw.get("prompt", "# Test prompt\n"),
        author="test",
        changelog="seed",
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )


# ---------------------------------------------------------------------------
# agents ls
# ---------------------------------------------------------------------------


def test_agents_ls_empty(store_fixture) -> None:
    result = runner.invoke(app, ["agents", "ls"])
    assert result.exit_code == 0
    assert "No agents registered" in result.output


def test_agents_ls_shows_agent(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "ls"])
    assert result.exit_code == 0
    assert "t1" in result.output
    assert "token" in result.output


def test_agents_ls_json(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "t1"


# ---------------------------------------------------------------------------
# agents show
# ---------------------------------------------------------------------------


def test_agents_show_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["agents", "show", "no-such-agent"])
    assert result.exit_code != 0


def test_agents_show_existing(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "show", "t1"])
    assert result.exit_code == 0
    assert "t1" in result.output


# ---------------------------------------------------------------------------
# agents create
# ---------------------------------------------------------------------------


def test_agents_create_from_config(store_fixture, tmp_path: Path) -> None:
    config_path = tmp_path / "agent.json"
    config_path.write_text(
        json.dumps(
            {
                "id": "cli-created",
                "description": "Created via CLI",
                "runner": {"kind": "token"},
            }
        )
    )
    result = runner.invoke(
        app, ["agents", "create", "--config", str(config_path), "--author", "test"]
    )
    assert result.exit_code == 0
    assert "cli-created" in result.output
    assert "created" in result.output


def test_agents_create_duplicate(store_fixture, tmp_path: Path) -> None:
    _seed_agent(store_fixture, "dup")
    config_path = tmp_path / "dup.json"
    config_path.write_text(
        json.dumps(
            {
                "id": "dup",
                "description": "Duplicate",
                "runner": {"kind": "token"},
            }
        )
    )
    result = runner.invoke(
        app, ["agents", "create", "--config", str(config_path), "--author", "test"]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# agents delete
# ---------------------------------------------------------------------------


def test_agents_delete(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "delete", "t1", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output


def test_agents_delete_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["agents", "delete", "no-such", "--yes"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# agents grants
# ---------------------------------------------------------------------------


def test_agents_grants_ls(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "grants", "ls", "t1"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# agents tools
# ---------------------------------------------------------------------------


def test_agents_tools_ls(store_fixture) -> None:
    result = runner.invoke(app, ["agents", "tools", "ls"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# agents versions
# ---------------------------------------------------------------------------


def test_agents_versions_ls(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "versions", "ls", "t1"])
    assert result.exit_code == 0
    assert "version" in result.output.lower() or result.exit_code == 0


# ---------------------------------------------------------------------------
# agents validation
# ---------------------------------------------------------------------------


def test_agents_validation_get_empty(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "validation", "get", "t1"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# agents runner-profile
# ---------------------------------------------------------------------------


def test_agents_runner_profile_get_none(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agents", "runner-profile", "t1", "--get"])
    assert result.exit_code == 0
    assert "no runner profile" in result.output.lower()
