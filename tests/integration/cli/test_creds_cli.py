"""Integration tests for ``agentbox ops creds`` CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentbox.cli import app
from agentbox.core.engines.credentials import clear as creds_clear

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clear_creds_registry() -> None:
    """Reset the credential registry so each test sees the built-in set."""
    import importlib

    creds_clear()
    import agentbox.core.engines.credentials.builtin as reg

    importlib.reload(reg)
    yield
    creds_clear()
    importlib.reload(reg)


# ---------------------------------------------------------------------------
# Help / tree
# ---------------------------------------------------------------------------


def test_creds_help() -> None:
    result = runner.invoke(app, ["engine", "creds", "--help"])
    assert result.exit_code == 0
    assert "setup" in result.output
    assert "status" in result.output
    assert "import" in result.output
    assert "clear" in result.output


def test_creds_status_output() -> None:
    result = runner.invoke(app, ["engine", "creds", "status"])
    assert result.exit_code == 0
    assert "Credential Status" in result.output
    # Should list all registered backends
    assert "claude" in result.output
    assert "openai" in result.output


def test_creds_setup_help() -> None:
    result = runner.invoke(app, ["engine", "creds", "setup", "--help"])
    assert result.exit_code == 0
    assert "--all" in result.output


def test_creds_setup_all_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup --all against a registry should exit 0 even when things are missing."""
    # Pre-set env vars so detection shows PRESENT and methods are skipped
    # (avoids interactive getpass prompts that hang in CliRunner)
    for var in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
        "XAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
    ):
        monkeypatch.setenv(var, "sk-test1234567890abcdef")
    # Mock subprocess.run to prevent interactive login commands from hanging
    import subprocess

    def _fake_run(*args: object, **kwargs: object) -> object:
        class _Completed:
            returncode = 1
        return _Completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = runner.invoke(app, ["engine", "creds", "setup", "--all"])
    assert result.exit_code == 0


def test_creds_setup_unknown_backend() -> None:
    result = runner.invoke(app, ["engine", "creds", "setup", "nonexistent"])
    assert result.exit_code == 1
    assert "Unknown backend" in result.output


def test_creds_import_unknown_backend() -> None:
    result = runner.invoke(app, ["engine", "creds", "import", "nonexistent"])
    assert result.exit_code == 1
    assert "Unknown backend" in result.output


def test_creds_clear_unknown_backend() -> None:
    result = runner.invoke(app, ["engine", "creds", "clear", "nonexistent"])
    assert result.exit_code == 1
    assert "Unknown backend" in result.output


# ---------------------------------------------------------------------------
# Doctor integration
# ---------------------------------------------------------------------------


def test_doctor_includes_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("# test\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(app, ["system", "doctor"])
    assert result.exit_code in (0, 1)
    assert "Credentials" in result.output


def _clear_deps_caches() -> None:
    import agentbox.cli._deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
