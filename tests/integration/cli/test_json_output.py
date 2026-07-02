"""Verify --json output on core CLI commands produces valid, parseable JSON."""

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
    get_db,
)

runner = CliRunner()


def _clear_deps_caches() -> None:
    for fn in (get_settings, get_db, get_executor, get_mcp_registry, get_engine_service):
        fn.cache_clear()


@pytest.fixture
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    manifest = tmp_path / "agentbox.toml"
    manifest.write_text("# test manifest\n")
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    _clear_deps_caches()
    yield tmp_path
    _clear_deps_caches()


def test_runs_ls_json_empty(db_env: Path) -> None:
    result = runner.invoke(app, ["history", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


def test_runs_show_json_nonexistent(db_env: Path) -> None:
    result = runner.invoke(app, ["history", "show", "nonexistent", "--json"])
    assert result.exit_code != 0
    assert "no such run" in result.output.lower()


def test_agents_ls_json_empty(db_env: Path) -> None:
    result = runner.invoke(app, ["agent", "def", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


def test_runners_profiles_ls_json_empty(db_env: Path) -> None:
    result = runner.invoke(app, ["engine", "profile", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


def test_runners_backends_ls_json() -> None:
    result = runner.invoke(app, ["engine", "backend", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    for entry in parsed:
        assert "id" in entry
        assert "label" in entry


def test_agents_ls_empty(db_env: Path) -> None:
    result = runner.invoke(app, ["agent", "def", "ls"])
    assert result.exit_code == 0
    assert "No agents registered" in result.output


def test_runs_ls_empty(db_env: Path) -> None:
    result = runner.invoke(app, ["history", "ls"])
    assert result.exit_code == 0
    assert "No runs yet" in result.output


def test_runners_profiles_ls_empty(db_env: Path) -> None:
    result = runner.invoke(app, ["engine", "profile", "ls"])
    assert result.exit_code == 0
    assert "No runner profiles found" in result.output


def test_runners_backends_ls() -> None:
    result = runner.invoke(app, ["engine", "backend", "ls"])
    assert result.exit_code == 0
    assert "Runner Backends" in result.output
