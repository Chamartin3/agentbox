"""Test manifest patch endpoint writes to DB only (no disk)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def manifest_with_agent(tmp_path: Path) -> Path:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        """\
[[agents]]
id = "test.patch_agent"
description = "before"
session_mode = "headless"
workspace = "default"
tags = ["old"]
tools = ["tool1"]

  [agents.runner]
  kind = "claude_code"
  model = "haiku"
  timeout_seconds = 120
"""
    )
    return manifest


def test_patch_agent_creates_db_version(
    client: Any, isolated_data_dir: Path, manifest_with_agent: Path
) -> None:
    """PATCH /api/manifest/agents/{id} should create a new agent_versions row."""
    import agentbox.api.deps as deps

    # Point the loader at our manifest and clear caches.
    deps.get_settings.cache_clear()
    deps.get_loader.cache_clear()
    deps.get_store.cache_clear()

    # Seed the DB with the agent from disk.
    from agentbox.api.app import create_app
    from fastapi.testclient import TestClient

    # Re-create client so startup sweep imports the agent into DB.
    with TestClient(create_app()) as c:
        # Verify the agent exists.
        resp = c.get("/api/agents/test.patch_agent")
        assert resp.status_code == 200
        before = resp.json()
        assert before["agent"]["description"] == "before"
        assert before["agent"]["tags"] == ["old"]

        # Patch description and tags.
        resp = c.patch(
            "/api/manifest/agents/test.patch_agent",
            json={
                "description": "after",
                "tags": ["new"],
                "tools": ["tool2"],
                "webhook_url": "http://example.com",
                "headless": True,
            },
        )
        assert resp.status_code == 200
        patched = resp.json()
        assert patched["agent"]["description"] == "after"
        assert patched["agent"]["tags"] == ["new"]
        assert patched["agent"]["tools"] == ["tool2"]
        assert patched["agent"]["webhook_url"] == "http://example.com"
        assert patched["agent"]["headless"] is True

        # Re-fetch and verify persistence.
        resp = c.get("/api/agents/test.patch_agent")
        assert resp.status_code == 200
        after = resp.json()
        assert after["agent"]["description"] == "after"
        assert after["agent"]["tags"] == ["new"]
        assert after["agent"]["tools"] == ["tool2"]
        assert after["agent"]["webhook_url"] == "http://example.com"
        assert after["agent"]["headless"] is True

        # Verify a new DB version was created.
        store = deps.get_store()
        versions = store.list_versions("test.patch_agent")
        assert len(versions) >= 2  # initial import + patch
        latest = versions[0]
        assert latest["author"] == "api:patch"
        assert "description" in latest["changelog"]

        # Verify agent_sync was populated.
        sync_meta = store.get_agent_sync("test.patch_agent")
        assert sync_meta is not None
        assert sync_meta["proxy_path"] == str(manifest_with_agent)
