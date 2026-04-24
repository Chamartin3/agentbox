"""mf check: valid manifest → exit 0; missing/broken → exit 1."""

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


def test_mf_check_good(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n[[agents]]\nid = 'test_agent'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(app, ["mf", "check"])
    assert result.exit_code == 0
    assert "OK" in result.output or "manifest OK" in result.output


def test_mf_check_bad_syntax(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("{{bad toml syntax!!!}}")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(app, ["mf", "check"])
    assert result.exit_code == 1


def test_mf_check_missing(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.toml"
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(missing))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(app, ["mf", "check"])
    assert result.exit_code == 1
