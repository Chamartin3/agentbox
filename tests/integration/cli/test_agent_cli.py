"""Smoke tests for agent CLI commands — updated for 6-subgroup branch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentbox.cli import app
from agentbox.cli.shared import (
    get_executor,
    get_mcp_registry,
    get_settings,
    get_store,
)
from agentbox.cli.shared import get_store as _get_store
from agentbox.core.db import AgentDef

runner = CliRunner()


def _clear_deps_caches() -> None:
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
    store = _get_store()
    yield store
    _clear_deps_caches()


def _seed_agent(store, agent_id: str = "t1", **kw) -> dict:
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
# agent def ls
# ---------------------------------------------------------------------------


def test_def_ls_empty(store_fixture) -> None:
    result = runner.invoke(app, ["agent", "def", "ls"])
    assert result.exit_code == 0
    assert "No agents registered" in result.output


def test_def_ls_shows_agent(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "def", "ls"])
    assert result.exit_code == 0
    assert "t1" in result.output
    assert "token" in result.output


def test_def_ls_json(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "def", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "t1"


# ---------------------------------------------------------------------------
# agent def show
# ---------------------------------------------------------------------------


def test_def_show_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["agent", "def", "show", "no-such-agent"])
    assert result.exit_code != 0


def test_def_show_existing(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "def", "show", "t1"])
    assert result.exit_code == 0
    assert "t1" in result.output


# ---------------------------------------------------------------------------
# agent def new
# ---------------------------------------------------------------------------


def test_def_new_from_config(store_fixture, tmp_path: Path) -> None:
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
        app, ["agent", "def", "new", "--config", str(config_path), "--author", "test"]
    )
    assert result.exit_code == 0
    assert "cli-created" in result.output
    assert "created" in result.output


def test_def_new_duplicate(store_fixture, tmp_path: Path) -> None:
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
        app, ["agent", "def", "new", "--config", str(config_path), "--author", "test"]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# agent def rm
# ---------------------------------------------------------------------------


def test_def_rm(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "def", "rm", "t1", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output


def test_def_rm_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["agent", "def", "rm", "no-such", "--yes"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# agent tool ls (grants)
# ---------------------------------------------------------------------------


def test_tool_grants_ls(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "tool", "ls", "--agent", "t1"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# agent tool ls (global)
# ---------------------------------------------------------------------------


def test_tool_ls(store_fixture) -> None:
    result = runner.invoke(app, ["agent", "tool", "ls"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# agent version ls
# ---------------------------------------------------------------------------


def test_version_ls(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "version", "ls", "t1"])
    assert result.exit_code == 0
    assert "version" in result.output.lower() or result.exit_code == 0


# ---------------------------------------------------------------------------
# agent check get
# ---------------------------------------------------------------------------


def test_check_get_empty(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "check", "get", "t1"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# agent def edit --runner
# ---------------------------------------------------------------------------


def test_def_edit_runner_get_none(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["agent", "def", "edit", "t1", "--runner", "clear"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()
