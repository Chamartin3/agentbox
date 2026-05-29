"""Smoke tests for runs CLI commands."""

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


def test_runs_ls_empty(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "ls"])
    assert r.exit_code == 0
    assert "No runs yet" in r.output


def test_runs_ls_json_empty(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "ls", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output) == []


def test_runs_show_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "show", "x"])
    assert r.exit_code != 0
    assert "no such run" in r.output.lower()


def test_runs_stats_empty(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "stats"])
    assert r.exit_code == 0
    assert "total_runs" in json.loads(r.output)


def test_runs_facets_empty(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "facets"])
    assert r.exit_code == 0
    assert "agents" in json.loads(r.output)


def test_runs_cancel_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "cancel", "x"])
    assert r.exit_code != 0


def test_runs_prompt_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "prompt", "x"])
    assert r.exit_code != 0


def test_runs_transcript_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "transcript", "x"])
    assert r.exit_code != 0


def test_runs_post_outcome_not_found(store_fixture) -> None:
    r = runner.invoke(app, ["runs", "post-outcome", "x", "deployed"])
    assert r.exit_code != 0
