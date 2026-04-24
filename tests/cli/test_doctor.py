"""doctor: runs checks and exits 0 or 1."""

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


def test_doctor_with_minimal_manifest(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("project = 'test'\n")
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(app, ["doctor"])
    # doctor should exit with number of failures (capped at 1)
    assert result.exit_code in (0, 1)
    assert "Manifest exists" in result.output
