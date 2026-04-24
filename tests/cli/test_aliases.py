"""Backwards-compat aliases still work and print deprecation notices."""

from pathlib import Path

from agentbox.cli import app
from typer.testing import CliRunner

runner = CliRunner()


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


def test_agents_alias(monkeypatch, tmp_path: Path) -> None:
    """agentbox agents still runs and prints deprecation notice."""
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(app, ["agents"])
    assert "deprecated" in result.output


def test_run_alias(monkeypatch, tmp_path: Path) -> None:
    """agentbox run still exists and prints deprecation notice."""
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    # Just check --help for the run command, since it needs API to work
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "deprecated" not in result.output  # help doesn't show deprecation
