"""Verify every sub-app's --help shows the expected commands."""

from agentbox.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_root_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for grp in (
        "agents",
        "runs",
        "runners",
        "workspaces",
        "resources",
        "analytics",
        "system",
        "ops",
        "serve",
        "exec",
        "doctor",
    ):
        assert grp in result.output


def test_agents_help() -> None:
    result = runner.invoke(app, ["agents", "--help"])
    assert result.exit_code == 0
    for sub in ("ls", "show", "create", "edit", "delete", "draft", "publish",
                "rollback", "runner-profile", "files", "prompt"):
        assert sub in result.output

    # Sub-apps registered on agents
    for sub_app in ("grants", "prompts", "tools", "validation", "versions"):
        assert sub_app in result.output


def test_workspaces_help() -> None:
    result = runner.invoke(app, ["workspaces", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "path" in result.output


def test_runs_help() -> None:
    result = runner.invoke(app, ["runs", "--help"])
    assert result.exit_code == 0
    for sub in ("ls", "show", "tail", "stats", "facets", "comments",
                "prompt", "transcript", "post-outcome", "cancel"):
        assert sub in result.output


def test_ops_help() -> None:
    result = runner.invoke(app, ["ops", "--help"])
    assert result.exit_code == 0
    assert "cfg" in result.output
    assert "migrate" in result.output
    assert "launch" in result.output


def test_system_help() -> None:
    result = runner.invoke(app, ["system", "--help"])
    assert result.exit_code == 0
    for sub in ("env", "health", "host", "mcp", "project", "settings", "tokens"):
        assert sub in result.output


def test_runners_help() -> None:
    result = runner.invoke(app, ["runners", "--help"])
    assert result.exit_code == 0
    assert "profiles" in result.output
    assert "providers" in result.output
    assert "backends" in result.output


def test_analytics_help() -> None:
    result = runner.invoke(app, ["analytics", "--help"])
    assert result.exit_code == 0
    assert "activity" in result.output
    assert "usage" in result.output


def test_resources_help() -> None:
    result = runner.invoke(app, ["resources", "--help"])
    assert result.exit_code == 0
    assert "repo" in result.output
    assert "bindings" in result.output


def test_agents_grants_help() -> None:
    result = runner.invoke(app, ["agents", "grants", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "add" in result.output
    assert "rm" in result.output


def test_agents_tools_help() -> None:
    result = runner.invoke(app, ["agents", "tools", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output


def test_agents_versions_help() -> None:
    result = runner.invoke(app, ["agents", "versions", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output


def test_system_health_help() -> None:
    result = runner.invoke(app, ["system", "health", "--help"])
    assert result.exit_code == 0
    assert "check" in result.output


def test_system_tokens_help() -> None:
    result = runner.invoke(app, ["system", "tokens", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output


def test_workspaces_mcp_help() -> None:
    result = runner.invoke(app, ["workspaces", "mcp", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output


def test_workspaces_skills_help() -> None:
    result = runner.invoke(app, ["workspaces", "skills", "--help"])
    assert result.exit_code == 0
    assert "ls" in result.output
    assert "show" in result.output
