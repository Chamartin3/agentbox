"""Verify every sub-app's --help shows the expected commands (new 7-branch tree)."""

from agentbox.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for grp in ("agent", "run", "work", "engine", "system", "ops", "history"):
        assert grp in result.output


def test_agent_help() -> None:
    result = runner.invoke(app, ["agent", "--help"])
    assert result.exit_code == 0
    for sub in ("def", "prompt", "version", "tool", "check", "files"):
        assert sub in result.output


def test_agent_def_help() -> None:
    result = runner.invoke(app, ["agent", "def", "--help"])
    assert result.exit_code == 0
    for cmd in ("ls", "show", "new", "edit", "rm"):
        assert cmd in result.output


def test_work_help() -> None:
    result = runner.invoke(app, ["work", "--help"])
    assert result.exit_code == 0
    assert "ws" in result.output
    assert "mcp" in result.output


def test_run_cmd_help() -> None:
    """run is a unified command (not a group) — check its option flags."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    # Core options of the unified run command
    assert "--prompt" in result.output
    assert "--backend" in result.output
    assert "--workspace" in result.output


def test_history_help() -> None:
    result = runner.invoke(app, ["history", "--help"])
    assert result.exit_code == 0
    for cmd in ("ls", "show", "cancel", "log", "stat"):
        assert cmd in result.output


def test_history_log_help() -> None:
    result = runner.invoke(app, ["history", "log", "--help"])
    assert result.exit_code == 0
    for sub in ("tail", "transcript", "prompt", "comments", "outcome"):
        assert sub in result.output


def test_ops_help() -> None:
    result = runner.invoke(app, ["ops", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "cfg" in result.output
    # migrate has been removed — all toml-era migrations are done
    assert "resource" in result.output


def test_system_help() -> None:
    result = runner.invoke(app, ["system", "--help"])
    assert result.exit_code == 0
    for sub in ("doctor", "env", "health", "host", "mcp", "project", "settings"):
        assert sub in result.output


def test_engine_help() -> None:
    result = runner.invoke(app, ["engine", "--help"])
    assert result.exit_code == 0
    assert "profile" in result.output
    assert "provider" in result.output
    assert "backend" in result.output
    assert "cred" in result.output


def test_ops_resources_help() -> None:
    result = runner.invoke(app, ["ops", "resource", "--help"])
    assert result.exit_code == 0
    assert "repo" in result.output
    assert "bind" in result.output


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




def test_work_mcp_help() -> None:
    result = runner.invoke(app, ["work", "mcp", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output


def test_work_skills_help() -> None:
    result = runner.invoke(app, ["work", "skill", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
