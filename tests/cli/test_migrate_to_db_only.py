"""Test migrate-to-db-only command."""

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


def test_migrate_to_db_only_flips_meta(monkeypatch, tmp_path: Path) -> None:
    """Test migrate-to-db-only command flips sync_mode and export_to_disk."""
    # Set up minimal manifest
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    agent_dir = agents_dir / "test_agent"
    agent_dir.mkdir()

    agent_toml = agent_dir / "agent.toml"
    agent_toml.write_text(
        """id = "test_agent"
description = "Test agent"

[runner]
kind = "token"
"""
    )

    manifest = tmp_path / "agentbox.toml"
    manifest.write_text(
        f"""project = "test"
manifest_dir = "{agents_dir}"
"""
    )

    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    # Initialize the store and create v1
    from agentbox.api.deps import get_loader, get_store

    store = get_store()
    loader = get_loader()

    # Load manifest to trigger startup_sweep (v1 creation)
    manifest_obj = loader.load()
    agent = [a for a in manifest_obj.agents if a.id == "test_agent"][0]

    from agentbox.core.prompt.versioning.drift import startup_sweep

    startup_sweep([agent], store, project_root=tmp_path)

    # Verify v1 was created
    versions = store.list_versions("test_agent")
    assert len(versions) == 1
    assert versions[0]["is_draft"] == 0  # Published

    # Activate the version (startup_sweep doesn't do this for NEW agents)
    store.activate_version("test_agent", versions[0]["id"])

    # Initialize agent_meta (normally done by watcher on NEW agent)
    store.init_agent_meta(
        "test_agent",
        sync_mode="watch",
        export_to_disk=True,
        source_path=str(agent.source_path),
    )

    # Verify agent_meta exists with default sync_mode="watch"
    meta = store.get_agent_meta("test_agent")
    assert meta is not None
    assert meta["sync_mode"] == "watch"

    # Run migrate command
    result = runner.invoke(
        app, ["migrate", "to-db-only", "test_agent"]
    )
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    assert "migrated" in result.output.lower()
    assert "sync_mode: watch → off" in result.output

    # Verify agent_meta was updated
    _clear_deps_caches()
    store = get_store()
    meta = store.get_agent_meta("test_agent")
    assert meta is not None
    assert meta["sync_mode"] == "off"
    assert bool(meta["export_to_disk"]) is True


def test_migrate_to_db_only_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    """Test migrate-to-db-only is idempotent — running twice creates no new versions."""
    # Setup
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    agent_dir = agents_dir / "test_agent"
    agent_dir.mkdir()

    agent_toml = agent_dir / "agent.toml"
    agent_toml.write_text(
        """id = "test_agent"
description = "Test agent"

[runner]
kind = "token"
"""
    )

    manifest = tmp_path / "agentbox.toml"
    manifest.write_text(
        f"""project = "test"
manifest_dir = "{agents_dir}"
"""
    )

    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    from agentbox.api.deps import get_loader, get_store

    store = get_store()
    loader = get_loader()

    manifest_obj = loader.load()
    agent = [a for a in manifest_obj.agents if a.id == "test_agent"][0]

    from agentbox.core.prompt.versioning.drift import startup_sweep

    startup_sweep([agent], store, project_root=tmp_path)

    # Activate the version
    versions = store.list_versions("test_agent")
    store.activate_version("test_agent", versions[0]["id"])

    # Initialize agent_meta (normally done by watcher on NEW agent)
    store.init_agent_meta(
        "test_agent",
        sync_mode="watch",
        export_to_disk=True,
        source_path=str(agent.source_path),
    )

    # First run
    result1 = runner.invoke(
        app, ["migrate", "to-db-only", "test_agent"]
    )
    assert result1.exit_code == 0

    # Check version count after first run
    _clear_deps_caches()
    store = get_store()
    versions_after_first = store.list_versions("test_agent")
    first_count = len(versions_after_first)

    # Second run (should be idempotent)
    result2 = runner.invoke(
        app, ["migrate", "to-db-only", "test_agent"]
    )
    assert result2.exit_code == 0

    # Check version count after second run — should not have changed
    _clear_deps_caches()
    store = get_store()
    versions_after_second = store.list_versions("test_agent")
    second_count = len(versions_after_second)

    assert first_count == second_count


def test_migrate_to_db_only_missing_agent_errors(monkeypatch, tmp_path: Path) -> None:
    """Test migrate-to-db-only errors when agent doesn't exist."""
    manifest = tmp_path / "agentbox.toml"
    manifest.write_text('project = "test"\n')

    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest))
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    _clear_deps_caches()

    result = runner.invoke(
        app, ["migrate", "to-db-only", "nonexistent"]
    )
    assert result.exit_code == 1
    assert "no active version" in result.output.lower()
