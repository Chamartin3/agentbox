"""Verify every sub-app's --help shows the expected commands (6-branch tree)."""

from agentbox.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for grp in ("agent", "run", "work", "engine", "system", "ops"):
        assert grp in result.output


def test_agent_help() -> None:
    result = runner.invoke(app, ["agent", "--help"])
    assert result.exit_code == 0
    for sub in ("def", "prompt", "version", "tool", "check", "files"):
        assert sub in result.output


def test_agent_def_help() -> None:
    result = runner.invoke(app, ["agent", "def", "--help"])
    assert result.exit_code == 0
    for cmd in ("ls", "show", "new", "edit", "rm", "export"):
        assert cmd in result.output


def test_work_help() -> None:
    result = runner.invoke(app, ["work", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "path" in result.output


def test_run_runs_help() -> None:
    result = runner.invoke(app, ["run", "runs", "--help"])
    assert result.exit_code == 0
    for sub in ("ls", "show", "tail", "stats", "facets", "comments",
                "prompt", "transcript", "post-outcome", "cancel"):
        assert sub in result.output


def test_ops_help() -> None:
    result = runner.invoke(app, ["ops", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "cfg" in result.output
    assert "migrate" in result.output
    assert "launch" in result.output
    assert "resources" in result.output


def test_system_help() -> None:
    result = runner.invoke(app, ["system", "--help"])
    assert result.exit_code == 0
    for sub in ("doctor", "env", "health", "host", "mcp", "project", "settings", "tokens"):
        assert sub in result.output


def test_engine_help() -> None:
    result = runner.invoke(app, ["engine", "--help"])
    assert result.exit_code == 0
    assert "profiles" in result.output
    assert "providers" in result.output
    assert "backends" in result.output
    assert "creds" in result.output


def test_run_feedback_help() -> None:
    result = runner.invoke(app, ["run", "feedback", "--help"])
    assert result.exit_code == 0
    assert "activity" in result.output
    assert "usage" in result.output


def test_ops_resources_help() -> None:
    result = runner.invoke(app, ["ops", "resources", "--help"])
    assert result.exit_code == 0
    assert "repo" in result.output
    assert "bindings" in result.output


def test_agent_tool_help() -> None:
    result = runner.invoke(app, ["agent", "tool", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
    assert "grant" in result.output
    assert "revoke" in result.output


def test_agent_version_help() -> None:
    result = runner.invoke(app, ["agent", "version", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
    assert "new" in result.output
    assert "note" in result.output


def test_system_health_help() -> None:
    result = runner.invoke(app, ["system", "health", "--help"])
    assert result.exit_code == 0
    assert "check" in result.output


def test_system_tokens_help() -> None:
    result = runner.invoke(app, ["system", "tokens", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output


def test_work_mcp_help() -> None:
    result = runner.invoke(app, ["work", "mcp", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output


def test_work_skills_help() -> None:
    result = runner.invoke(app, ["work", "skills", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
