"""Tests for manifest-free startup.

Verify that agentbox can start and serve requests when:
- No agentbox.toml / manifest file exists on disk
- Agents exist only in the DB (created via API)
- Or when the DB is empty (bootstrap mode)
"""

from __future__ import annotations

from pathlib import Path

import pytest

import agentbox.api.deps as _deps
from agentbox.api.app import create_app
from fastapi.testclient import TestClient


def test_startup_with_no_manifest_and_empty_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """App starts successfully with no manifest and no DB agents."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))

    # Clear caches so the next call reads the new env vars
    for fn in (
        _deps.get_settings,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()

    # Create the app — should not raise
    app = create_app()
    assert app is not None

    # Health check should pass
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200

    # Clear caches again for good measure
    for fn in (
        _deps.get_settings,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()


def test_agents_list_endpoint_empty_in_manifest_free_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/agents returns empty list in manifest-free mode with no DB agents."""
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))

    # Clear caches
    for fn in (
        _deps.get_settings,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    # Clear caches again
    for fn in (
        _deps.get_settings,
        _deps.get_executor,
        _deps.get_mcp_registry,
    ):
        fn.cache_clear()
