"""Verify every sub-app's --help shows the expected commands."""

from agentbox.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "agent" in result.output
    assert "ws" in result.output
    assert "runs" in result.output
    assert "cfg" in result.output
    assert "mcp" in result.output
    assert "migrate" in result.output
    assert "serve" in result.output
    assert "exec" in result.output
    assert "doctor" in result.output


def test_agent_help() -> None:
    result = runner.invoke(app, ["agent", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
    assert "prompt" in result.output


def test_ws_help() -> None:
    result = runner.invoke(app, ["ws", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "path" in result.output
    assert "new" in result.output
    assert "reset" in result.output
    assert "edit" in result.output


def test_runs_help() -> None:
    result = runner.invoke(app, ["runs", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
    assert "tail" in result.output


def test_cfg_help() -> None:
    result = runner.invoke(app, ["cfg", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output
    assert "paths" in result.output
    assert "gen" in result.output


def test_mcp_help() -> None:
    result = runner.invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output


def test_migrate_help() -> None:
    result = runner.invoke(app, ["migrate", "--help"])
    assert result.exit_code == 0
    assert "ws-perms" in result.output
