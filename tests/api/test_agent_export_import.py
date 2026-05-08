"""Tests for /api/manifest/agents/{id}/export and /api/manifest/agents/import endpoints."""

from __future__ import annotations

import contextlib
from pathlib import Path

from agentbox.api.app import create_app
from fastapi.testclient import TestClient


class _ManagedTestClient(TestClient):
    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.__exit__(None, None, None)


def _app(tmp_path: Path):
    """Clear DI, create app with startup triggered, return (client, store).

    Uses explicit __enter__ instead of a with-block so the returned client
    stays alive for the caller to make requests against.
    """
    import agentbox.api.deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()
    client = _ManagedTestClient(create_app())
    client.__enter__()
    store = deps.get_store()
    return client, store


class TestExportAgent:
    def test_export_missing_agent_returns_404(self, isolated_data_dir: Path) -> None:
        """Exporting a non-existent agent returns 404."""
        client, _ = _app(isolated_data_dir)
        resp = client.post(
            "/api/manifest/agents/nonexistent/export",
            json={"source_format": "markdown"},
        )
        assert resp.status_code == 404
        assert "unknown_agent" in resp.text.lower() or "not found" in resp.text.lower()

    def test_export_db_agent_writes_markdown(self, isolated_data_dir: Path) -> None:
        """Create a DB-only agent, export as markdown, verify file exists."""
        client, store = _app(isolated_data_dir)

        # Create a DB-only agent (no backing file)
        agent_id = "test_export_agent"
        config = {
            "id": agent_id,
            "description": "Test agent for export",
            "runner": {"kind": "token"},
        }
        store.create_agent(
            agent_id=agent_id,
            config_json=config,
            author="test",
            changelog="initial",
            source="ui",
            export_to_disk=False,
        )
        # Publish to make it active
        store.publish_version(agent_id, 1, "test")

        # Export as markdown
        resp = client.post(
            f"/api/manifest/agents/{agent_id}/export",
            json={"source_format": "markdown"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_format"] == "markdown"
        assert len(data["written_files"]) > 0

        # Verify file exists on disk
        file_path = Path(data["source_path"])
        assert file_path.exists()
        assert file_path.suffix == ".md"

    def test_export_sets_agent_meta(self, isolated_data_dir: Path) -> None:
        """Verify export updates agent_meta with source_path and export_to_disk."""
        client, store = _app(isolated_data_dir)

        agent_id = "test_meta_agent"
        config = {
            "id": agent_id,
            "description": "Test",
            "runner": {"kind": "token"},
        }
        store.create_agent(
            agent_id=agent_id,
            config_json=config,
            author="test",
            changelog="initial",
            source="ui",
        )
        store.publish_version(agent_id, 1, "test")

        # Export
        resp = client.post(
            f"/api/manifest/agents/{agent_id}/export",
            json={"source_format": "standalone_toml"},
        )
        assert resp.status_code == 200

        # Check agent_meta was updated
        meta = store.get_agent_meta(agent_id)
        assert meta is not None
        assert meta.get("source_format") == "standalone_toml"
        assert meta.get("export_to_disk") == 1  # DB stores as int


class TestImportAgent:
    def test_import_new_agent_creates_draft(self, isolated_data_dir: Path) -> None:
        """Import a minimal agent.md file, verify it appears in store as draft."""
        client, store = _app(isolated_data_dir)

        # Write a minimal agent.md
        agents_d = isolated_data_dir / "agents.d"
        agents_d.mkdir(parents=True, exist_ok=True)
        agent_file = agents_d / "imported_agent.md"
        agent_file.write_text(
            """---
id: imported_agent
description: Imported test agent
runner:
  kind: token
---

# System Prompt

This is a test agent."""
        )

        # Import
        resp = client.post(
            "/api/manifest/agents/import",
            json={
                "path": str(agent_file),
                "strategy": "new_agent",
                "author": "test",
                "changelog": "import test",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == "imported_agent"
        assert data["version"] == 1
        assert data["is_draft"] is True
        assert data["skipped"] is False

        # Verify in store
        latest = store.latest_version("imported_agent")
        assert latest is not None
        assert latest["version"] == 1

    def test_import_duplicate_with_new_agent_strategy_returns_409(
        self, isolated_data_dir: Path
    ) -> None:
        """Importing with new_agent strategy when agent exists returns 409."""
        client, store = _app(isolated_data_dir)

        # Create existing agent
        agent_id = "existing_agent"
        config = {
            "id": agent_id,
            "description": "Existing",
            "runner": {"kind": "token"},
        }
        store.create_agent(
            agent_id=agent_id,
            config_json=config,
            author="test",
            changelog="initial",
        )

        # Write import file
        agents_d = isolated_data_dir / "agents.d"
        agents_d.mkdir(parents=True, exist_ok=True)
        agent_file = agents_d / "existing_agent.md"
        agent_file.write_text(
            """---
id: existing_agent
description: Updated description
runner:
  kind: token
---

Updated prompt"""
        )

        # Try to import as new_agent (should fail)
        resp = client.post(
            "/api/manifest/agents/import",
            json={
                "path": str(agent_file),
                "strategy": "new_agent",
                "author": "test",
                "changelog": "import test",
            },
        )
        assert resp.status_code == 409
        assert "agent_exists" in resp.text.lower() or "exists" in resp.text.lower()

    def test_import_duplicate_with_new_version_strategy(
        self, isolated_data_dir: Path
    ) -> None:
        """Import with new_version creates a new draft version."""
        client, store = _app(isolated_data_dir)

        # Create existing agent
        agent_id = "versioned_agent"
        config = {
            "id": agent_id,
            "description": "v1",
            "runner": {"kind": "token"},
        }
        store.create_agent(
            agent_id=agent_id,
            config_json=config,
            author="test",
            changelog="initial",
        )
        store.publish_version(agent_id, 1, "v1.0")

        # Write updated agent file
        agents_d = isolated_data_dir / "agents.d"
        agents_d.mkdir(parents=True, exist_ok=True)
        agent_file = agents_d / "versioned_agent.md"
        agent_file.write_text(
            """---
id: versioned_agent
description: v2 updated
runner:
  kind: token
---

Updated v2 prompt"""
        )

        # Import as new_version
        resp = client.post(
            "/api/manifest/agents/import",
            json={
                "path": str(agent_file),
                "strategy": "new_version",
                "author": "test2",
                "changelog": "update from file",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == agent_id
        assert data["version"] == 2
        assert data["is_draft"] is True

        # Verify both versions exist
        v1 = store.get_version(agent_id, 1)
        v2 = store.get_version(agent_id, 2)
        assert v1 is not None
        assert v2 is not None

    def test_import_invalid_file_returns_400(self, isolated_data_dir: Path) -> None:
        """Import with invalid path returns 400."""
        client, _ = _app(isolated_data_dir)

        resp = client.post(
            "/api/manifest/agents/import",
            json={
                "path": "/nonexistent/file.md",
                "strategy": "new_agent",
                "author": "test",
                "changelog": "test",
            },
        )
        assert resp.status_code == 400
        assert "file_not_found" in resp.text.lower() or "not found" in resp.text.lower()

    def test_import_skip_strategy(self, isolated_data_dir: Path) -> None:
        """Import with skip strategy returns skipped=true when agent exists."""
        client, store = _app(isolated_data_dir)

        # Create existing agent
        agent_id = "skip_agent"
        config = {
            "id": agent_id,
            "description": "Existing",
            "runner": {"kind": "token"},
        }
        store.create_agent(
            agent_id=agent_id,
            config_json=config,
            author="test",
            changelog="initial",
        )

        # Write file
        agents_d = isolated_data_dir / "agents.d"
        agents_d.mkdir(parents=True, exist_ok=True)
        agent_file = agents_d / "skip_agent.md"
        agent_file.write_text(
            """---
id: skip_agent
description: New
---

New prompt"""
        )

        # Import with skip
        resp = client.post(
            "/api/manifest/agents/import",
            json={
                "path": str(agent_file),
                "strategy": "skip",
                "author": "test",
                "changelog": "test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] is True

    def test_import_overwrite_strategy(self, isolated_data_dir: Path) -> None:
        """Import with overwrite creates and publishes a new version."""
        client, store = _app(isolated_data_dir)

        # Create existing agent
        agent_id = "overwrite_agent"
        config = {
            "id": agent_id,
            "description": "v1",
            "runner": {"kind": "token"},
        }
        store.create_agent(
            agent_id=agent_id,
            config_json=config,
            author="test",
            changelog="initial",
        )
        store.publish_version(agent_id, 1, "v1.0")

        # Write updated file
        agents_d = isolated_data_dir / "agents.d"
        agents_d.mkdir(parents=True, exist_ok=True)
        agent_file = agents_d / "overwrite_agent.md"
        agent_file.write_text(
            """---
id: overwrite_agent
description: v2 overwritten
---

Overwritten prompt"""
        )

        # Import with overwrite
        resp = client.post(
            "/api/manifest/agents/import",
            json={
                "path": str(agent_file),
                "strategy": "overwrite",
                "author": "test2",
                "changelog": "overwrite from file",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == agent_id
        assert data["version"] == 2
        assert data["is_draft"] is False  # Published

        # Verify active version is v2
        active = store.get_active_version(agent_id)
        assert active is not None
        assert active["version"] == 2
