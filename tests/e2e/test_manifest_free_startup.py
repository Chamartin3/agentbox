"""Tests for manifest-free startup (Phase 13e).

Verify that agentbox can start and serve requests when:
- No manifest.toml exists on disk
- Agents exist only in the DB (created via API)
- Or when both manifest and DB are empty (bootstrap mode)
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_startup_with_no_manifest_and_empty_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """App starts successfully with no manifest and no DB agents."""
    # Set up env for manifest-free mode: nonexistent manifest, isolated data dir
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "nonexistent.toml"))

    # Clear caches so the next call reads the new env vars
    import agentbox.api.deps as _deps

    for fn in (
        _deps.get_settings,
        _deps.get_store,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()

    # Create the app — should not raise
    from agentbox.api.app import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    assert app is not None

    # Health check should pass
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200

    # Clear caches again for good measure
    for fn in (
        _deps.get_settings,
        _deps.get_store,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()


def test_check_runtime_sources_allows_empty_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check_runtime_sources() returns True when both manifest and DB are empty."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "nonexistent.toml"))

    from agentbox.core.config import load_settings
    from agentbox.core.db import SessionStore

    settings = load_settings()
    store = SessionStore(tmp_path / "db.sqlite")

    # Should always return True
    assert settings.check_runtime_sources(store) is True


def test_check_runtime_sources_detects_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check_runtime_sources() returns True when manifest exists."""
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text("# test manifest\n")

    monkeypatch.setenv("AGENTBOX_MANIFEST", str(manifest_path))

    from agentbox.core.config import load_settings

    settings = load_settings()

    # Should return True because manifest exists
    assert settings.check_runtime_sources(None) is True


def test_check_runtime_sources_detects_db_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check_runtime_sources() returns True when DB has agents."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    nonexistent = str(tmp_path / "nonexistent.toml")
    monkeypatch.setenv("AGENTBOX_MANIFEST", nonexistent)

    from agentbox.core.config import load_settings
    from agentbox.core.db import SessionStore

    settings = load_settings()
    store = SessionStore(tmp_path / "db.sqlite")

    # Create a DB agent
    store.create_agent(
        agent_id="test-agent",
        config_json={"id": "test-agent"},
        author="test",
        changelog="test agent",
    )

    # Should return True because DB has agents
    assert settings.check_runtime_sources(store) is True


def test_agents_list_endpoint_empty_in_manifest_free_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/agents returns empty list in manifest-free mode with no DB agents."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "nonexistent.toml"))

    # Clear caches
    import agentbox.api.deps as _deps

    for fn in (
        _deps.get_settings,
        _deps.get_store,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()

    from agentbox.api.app import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    # Clear caches again
    for fn in (
        _deps.get_settings,
        _deps.get_store,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()
