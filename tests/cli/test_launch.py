"""agentbox launch — interactive launch surface across runners."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agentbox.cli import app
from typer.testing import CliRunner

cli = CliRunner()


def _clear_deps_caches() -> None:
    import agentbox.api.deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()


@pytest.fixture
def manifest_env(monkeypatch, tmp_path: Path) -> Path:
    """Set up a minimal manifest with a 'default' workspace + one agent."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "workdir" / "default").mkdir(parents=True)
    manifest = project / "agentbox.toml"
    manifest.write_text(
        """
project = "test"

[[workspaces]]
name = "default"
path = "workdir/default"

[[workspaces]]
name = "other"
path = "workdir/other"

[[agents]]
id = "demo"
prompt = "demo.md"
workspace = "other"
""".strip()
    )
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(project))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AGENTBOX_CREDS_DIR", str(tmp_path / "creds"))
    (tmp_path / "data").mkdir()
    _clear_deps_caches()
    return project


@pytest.fixture
def patched_run(monkeypatch):
    """Capture subprocess.run argv + cwd; stub ConfigGenerator output."""
    calls: list[dict[str, Any]] = []

    def fake_run(cmd, cwd=None, **_kw):
        calls.append({"cmd": list(cmd), "cwd": Path(cwd) if cwd else None})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("agentbox.cli.launch.subprocess.run", fake_run)

    class _StubGen:
        def generate_configs_into(self, gen_dir: Path) -> None:
            gen_dir = Path(gen_dir)
            (gen_dir / "claude_agents.json").write_text("[]")
            (gen_dir / "claude_mcp.json").write_text("{}")
            (gen_dir / "claude_settings.json").write_text("{}")

    monkeypatch.setattr(
        "agentbox.cli.launch._make_generator", lambda *_a, **_kw: _StubGen()
    )
    monkeypatch.setattr(
        "agentbox.cli.launch.shutil.which", lambda b: f"/usr/local/bin/{b}"
    )
    return calls


def test_launch_defaults_to_claude_in_default_workspace(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(app, ["launch"])
    assert result.exit_code == 0, result.output
    assert len(patched_run) == 1
    call = patched_run[0]
    assert call["cmd"][0] == "claude"
    # no agent → no --agent / --agents flags
    assert "--agent" not in call["cmd"]
    assert "--agents" not in call["cmd"]
    assert call["cwd"] == manifest_env / "workdir" / "default"


def test_launch_codex_runs_bare_cli(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(app, ["launch", "codex"])
    assert result.exit_code == 0, result.output
    cmd = patched_run[0]["cmd"]
    assert cmd[0] == "codex"
    # interactive — no `exec` subcommand, no --json
    assert "exec" not in cmd
    assert "--json" not in cmd


def test_launch_pi_runs_bare_cli(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(app, ["launch", "pi", "--model", "fast"])
    assert result.exit_code == 0, result.output
    cmd = patched_run[0]["cmd"]
    assert cmd[0] == "pi"
    assert "-p" not in cmd
    assert "--mode" not in cmd
    assert cmd[-2:] == ["--model", "fast"]


def test_launch_opencode_bare(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(app, ["launch", "opencode"])
    assert result.exit_code == 0, result.output
    cmd = patched_run[0]["cmd"]
    assert cmd[0] == "opencode"
    assert "run" not in cmd  # not the non-interactive subcommand
    assert "--format" not in cmd


def test_launch_with_agent_resolves_agent_workspace(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(app, ["launch", "claude", "--agent", "demo"])
    assert result.exit_code == 0, result.output
    call = patched_run[0]
    assert "--agent" in call["cmd"]
    # demo's declared workspace is "other"
    assert call["cwd"] == manifest_env / "workdir" / "other"


def test_launch_explicit_workspace_overrides_agent(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(
        app, ["launch", "claude", "--agent", "demo", "--workspace", "default"]
    )
    assert result.exit_code == 0, result.output
    assert patched_run[0]["cwd"] == manifest_env / "workdir" / "default"


def test_launch_token_runner_rejected(manifest_env: Path, patched_run) -> None:
    result = cli.invoke(app, ["launch", "token"])
    assert result.exit_code == 2
    assert "in-process" in result.output
    assert patched_run == []


def test_launch_unknown_runner_rejected(manifest_env: Path, patched_run) -> None:
    result = cli.invoke(app, ["launch", "bogus"])
    assert result.exit_code == 2
    assert "Unknown runner" in result.output
    assert patched_run == []


def test_launch_shell_runs_in_workspace_without_configs(
    manifest_env: Path, patched_run: list[dict[str, Any]], monkeypatch
) -> None:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    result = cli.invoke(app, ["launch", "shell"])
    assert result.exit_code == 0, result.output
    call = patched_run[0]
    assert call["cmd"] == ["/bin/zsh"]
    assert call["cwd"] == manifest_env / "workdir" / "default"
    # No legacy generated/ flat dump without --keep-configs.
    assert not (
        manifest_env / "workdir" / "default" / ".agentbox" / "generated"
    ).exists()
    # Sync provenance IS written, even on no-config launches.
    assert (
        manifest_env / "workdir" / "default" / ".agentbox" / "meta.json"
    ).exists()


def test_launch_shell_keeps_configs_when_flag_set(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    result = cli.invoke(app, ["launch", "shell", "--keep-configs"])
    assert result.exit_code == 0, result.output
    gen_dir = manifest_env / "workdir" / "default" / ".agentbox" / "generated"
    assert (gen_dir / "claude_agents.json").exists()
    # Persistent — must survive after launch returns
    assert gen_dir.exists()


def test_ws_shell_delegates_to_launch(
    manifest_env: Path, patched_run: list[dict[str, Any]]
) -> None:
    """`agentbox ws shell` should reach _launch_session with runner='shell'."""
    result = cli.invoke(app, ["ws", "shell", "other"])
    assert result.exit_code == 0, result.output
    assert patched_run[0]["cwd"] == manifest_env / "workdir" / "other"
    # ws shell defaults to --generate (keep_configs=True)
    assert (
        manifest_env / "workdir" / "other" / ".agentbox" / "generated"
    ).exists()


def test_launch_missing_binary_fails_gracefully(
    manifest_env: Path, patched_run, monkeypatch
) -> None:
    monkeypatch.setattr("agentbox.cli.launch.shutil.which", lambda _b: None)
    result = cli.invoke(app, ["launch", "pi"])
    assert result.exit_code == 127
    assert "not installed" in result.output
    assert patched_run == []


def test_launch_unknown_agent_rejected(manifest_env: Path, patched_run) -> None:
    result = cli.invoke(app, ["launch", "claude", "--agent", "nope"])
    assert result.exit_code == 1
    assert "Unknown agent" in result.output
    assert patched_run == []
