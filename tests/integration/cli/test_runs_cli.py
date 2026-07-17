"""Smoke tests for history CLI commands — happy paths against an in-memory store."""

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
    get_settings,
)
from agentbox.core.data import AgentDef
from agentbox.core.db.database import get_database
from agentbox.core.service.agents import AgentService

runner = CliRunner()


def _get_store():
    return get_database(str(get_settings().db_path))


def _clear_deps_caches() -> None:
    for fn in (get_settings, get_executor, get_mcp_registry):
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


def _seed_agent(store, agent_id: str = "t1") -> str:
    agent_def = AgentDef(
        id=agent_id,
        description="Test agent",
        runner={"kind": "token", "model": "gpt-4o"},
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
    return agent_id


# ---------------------------------------------------------------------------
# history ls
# ---------------------------------------------------------------------------


def test_runs_ls_empty(store_fixture) -> None:
    result = runner.invoke(app, ["history", "ls"])
    assert result.exit_code == 0
    assert "No runs yet" in result.output


def test_runs_ls_json_empty(store_fixture) -> None:
    result = runner.invoke(app, ["history", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed == []


def _seed_run_with_usage(store, agent_id: str = "t1") -> str:
    """Insert one finished run + usage row via the same service the CLI uses."""
    from agentbox.core.service.execution import ExecutionService

    svc = ExecutionService()
    run_id = svc.create_run(
        agent_id=agent_id, input_="hi", workdir="/tmp/x", transcript_path="/tmp/x.jsonl"
    )
    svc.finish_run(run_id, ok=True, output="done")
    svc.record_usage(
        run_id,
        {"model": "gpt-4o", "input_tokens": 12, "output_tokens": 3, "cost_usd": 0.01},
    )
    return run_id


def test_runs_ls_renders_row(store_fixture) -> None:
    """history ls builds RunSummary + renders the seeded run's usage totals.

    (Rich truncates per-cell content in the test's narrow terminal, so the
    exact id/status values are asserted by the --json test below; here we
    only prove one summary reached the table.)
    """
    _seed_agent(store_fixture)
    _seed_run_with_usage(store_fixture)
    result = runner.invoke(app, ["history", "ls"])
    assert result.exit_code == 0
    assert "Runs (latest 1)" in result.output


def test_runs_ls_json_dumps_summary(store_fixture) -> None:
    """--json dumps the RunSummary model with its typed usage nested."""
    _seed_agent(store_fixture)
    run_id = _seed_run_with_usage(store_fixture)
    result = runner.invoke(app, ["history", "ls", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert len(parsed) == 1
    row = parsed[0]
    assert row["id"] == run_id
    assert row["status"] == "ok"
    assert row["usage"]["input_tokens"] == 12
    assert row["usage"]["cost_usd"] == 0.01


# ---------------------------------------------------------------------------
# history show (not found)
# ---------------------------------------------------------------------------


def test_runs_show_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["history", "show", "nonexistent"])
    assert result.exit_code != 0
    assert "no such run" in result.output.lower()


# ---------------------------------------------------------------------------
# history stat (empty)
# ---------------------------------------------------------------------------


def test_runs_stats_empty(store_fixture) -> None:
    result = runner.invoke(app, ["history", "stat", "stats"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "totals" in parsed


def test_runs_facets_empty(store_fixture) -> None:
    result = runner.invoke(app, ["history", "stat", "facets"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "agents" in parsed


# ---------------------------------------------------------------------------
# history cancel (not found)
# ---------------------------------------------------------------------------


def test_runs_cancel_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["history", "cancel", "nonexistent"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# history log commands (not found via error handling)
# ---------------------------------------------------------------------------


def test_runs_comments_not_found(store_fixture) -> None:
    _seed_agent(store_fixture)
    result = runner.invoke(app, ["history", "log", "comments", "run-999"])
    assert result.exit_code != 0


def test_runs_prompt_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["history", "log", "prompt", "nonexistent"])
    assert result.exit_code != 0


def test_runs_transcript_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["history", "log", "transcript", "nonexistent"])
    assert result.exit_code != 0


def test_runs_post_outcome_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["history", "log", "outcome", "nonexistent", "deployed"])
    assert result.exit_code != 0
