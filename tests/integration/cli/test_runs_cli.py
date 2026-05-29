"""Smoke tests for runs CLI commands — happy paths against an in-memory store."""

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
        id=agent_id,
        description="Test agent",
        runner={"kind": "token", "model": "gpt-4o"},
    )
    store.create_agent(
        agent_id=agent_id,
        config_json=agent_def.model_dump(mode="python", exclude_none=True, warnings=False),
        prompt_content="# Test prompt\n",
        author="test",
        changelog="seed",
        source="cli",
        sync_mode="off",
        export_to_disk=False,
    )
    return agent_id


# ---------------------------------------------------------------------------
# runs ls
# ---------------------------------------------------------------------------


def test_runs_ls_empty(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "ls"])
    assert result.exit_code == 0
    assert "No runs yet" in result.output


def test_runs_ls_json_empty(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


# ---------------------------------------------------------------------------
# runs show (not found)
# ---------------------------------------------------------------------------


def test_runs_show_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "show", "nonexistent"])
    assert result.exit_code != 0
    assert "no such run" in result.output.lower()


# ---------------------------------------------------------------------------
# runs stats / facets (empty)
# ---------------------------------------------------------------------------


def test_runs_stats_empty(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "stats"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "total_runs" in parsed


def test_runs_facets_empty(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "facets"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "agents" in parsed


# ---------------------------------------------------------------------------
# runs cancel (not found)
# ---------------------------------------------------------------------------


def test_runs_cancel_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "cancel", "nonexistent"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# runs comments / prompt / post-outcome (not found via error handling)
# ---------------------------------------------------------------------------


def test_runs_comments_not_found(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["runs", "comments", "run-999"])
    assert result.exit_code != 0


def test_runs_prompt_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "prompt", "nonexistent"])
    assert result.exit_code != 0


def test_runs_transcript_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "transcript", "nonexistent"])
    assert result.exit_code != 0


def test_runs_post_outcome_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["runs", "post-outcome", "nonexistent", "deployed"])
    assert result.exit_code != 0
