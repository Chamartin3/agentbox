"""Tests for WorkspaceReadManager read methods (plan 118 Phase C)."""

from __future__ import annotations

import uuid

from agentbox.core.db import (
    AgentMetaManager,
    AgentVersionManager,
    ResourceBlobManager,
    ResourceManager,
    ResourceVersionManager,
    WorkspaceFileResourceBindingManager,
    WorkspaceManager,
    WorkspaceReadManager,
)
from agentbox.core.db.database import Database
from agentbox.core.data._util import now_iso


class TestWorkspaceReadManagerListFileBindings:
    """Test list_file_bindings parity with WorkspaceFileResourceBindingManager.list_for_workspace."""

    def test_parity_with_source_manager(self, db: Database) -> None:
        """Read manager returns same rows as source manager."""
        workspace_mgr: WorkspaceManager = db.workspaces
        resource_mgr: ResourceManager = db.resources
        binding_mgr: WorkspaceFileResourceBindingManager = (
            db.workspace_file_resource_bindings
        )
        read_mgr = WorkspaceReadManager(db._engine)

        # Create workspace and resource
        workspace = workspace_mgr.insert(name=f"test-ws-{uuid.uuid4().hex[:8]}")
        workspace_id = workspace["name"]
        resource = resource_mgr.create_resource(
            slug=f"test-res-{uuid.uuid4().hex[:8]}",
            type="document",
            display_name="Test Resource",
        )
        resource_id = resource["id"]

        binding_mgr.replace_for_workspace(
            workspace_id,
            [{"resource_id": resource_id}],
            reason="test",
        )

        # Compare results
        source_result = binding_mgr.list_for_workspace(workspace_id)
        read_result = read_mgr.list_file_bindings(workspace_id)
        assert read_result == source_result


class TestWorkspaceReadManagerGetResource:
    """Test get_resource parity with ResourceManager.get_resource."""

    def test_returns_none_for_missing_resource(self, db: Database) -> None:
        """Non-existent resource_id returns None."""
        read_mgr = WorkspaceReadManager(db._engine)
        result = read_mgr.get_resource("nonexistent")
        assert result is None

    def test_parity_with_source_manager(self, db: Database) -> None:
        """Read manager returns same row as source manager."""
        resource_mgr: ResourceManager = db.resources
        read_mgr = WorkspaceReadManager(db._engine)

        resource = resource_mgr.create_resource(
            slug=f"test-res-{uuid.uuid4().hex[:8]}",
            type="folder",
            display_name="Test Folder",
        )
        resource_id = resource["id"]

        source_result = resource_mgr.get_resource(resource_id)
        read_result = read_mgr.get_resource(resource_id)
        assert read_result == source_result


class TestWorkspaceReadManagerGetActiveResourceVersion:
    """Test get_active_resource_version parity with ResourceVersionManager.get_active_version."""

    def test_parity_with_source_manager(self, db: Database) -> None:
        """Read manager returns same row as source manager."""
        resource_mgr: ResourceManager = db.resources
        version_mgr: ResourceVersionManager = db.resource_versions
        read_mgr = WorkspaceReadManager(db._engine)

        resource = resource_mgr.create_resource(
            slug=f"test-res-{uuid.uuid4().hex[:8]}",
            type="document",
            display_name="Test",
        )
        resource_id = resource["id"]

        version_mgr.import_version(
            resource_id,
            [("test.txt", b"content", None, None)],
            import_source="upload",
            changelog="initial",
        )

        source_result = version_mgr.get_active_version(resource_id)
        read_result = read_mgr.get_active_resource_version(resource_id)
        assert read_result == source_result


class TestWorkspaceReadManagerGetResourceVersion:
    """Test get_resource_version parity with ResourceVersionManager.get_version."""

    def test_returns_none_for_missing_version(self, db: Database) -> None:
        """Non-existent version_id returns None."""
        read_mgr = WorkspaceReadManager(db._engine)
        result = read_mgr.get_resource_version("nonexistent")
        assert result is None

    def test_parity_with_source_manager(self, db: Database) -> None:
        """Read manager returns same row as source manager."""
        resource_mgr: ResourceManager = db.resources
        version_mgr: ResourceVersionManager = db.resource_versions
        read_mgr = WorkspaceReadManager(db._engine)

        resource = resource_mgr.create_resource(
            slug=f"test-res-{uuid.uuid4().hex[:8]}",
            type="document",
            display_name="Test",
        )
        resource_id = resource["id"]

        version = version_mgr.import_version(
            resource_id,
            [("test.txt", b"content", None, None)],
            import_source="upload",
            changelog="initial",
        )
        version_id = version["id"]

        source_result = version_mgr.get_version(version_id)
        read_result = read_mgr.get_resource_version(version_id)
        assert read_result == source_result


class TestWorkspaceReadManagerIterBlobs:
    """Test iter_blobs parity with ResourceBlobManager.iter_blobs."""

    def test_returns_empty_iterator_for_missing_version(self, db: Database) -> None:
        """Non-existent version_id yields nothing."""
        read_mgr = WorkspaceReadManager(db._engine)
        result = list(read_mgr.iter_blobs("nonexistent"))
        assert result == []

    def test_parity_with_source_manager(self, db: Database) -> None:
        """Read manager yields same blobs as source manager."""
        resource_mgr: ResourceManager = db.resources
        version_mgr: ResourceVersionManager = db.resource_versions
        blob_mgr: ResourceBlobManager = db.resource_blobs
        read_mgr = WorkspaceReadManager(db._engine)

        resource = resource_mgr.create_resource(
            slug=f"test-res-{uuid.uuid4().hex[:8]}",
            type="document",
            display_name="Test",
        )
        resource_id = resource["id"]

        version = version_mgr.import_version(
            resource_id,
            [("test.txt", b"content", "text/plain", "content")],
            import_source="upload",
            changelog="initial",
        )
        version_id = version["id"]

        source_result = list(blob_mgr.iter_blobs(version_id))
        read_result = list(read_mgr.iter_blobs(version_id))
        assert read_result == source_result


class TestWorkspaceReadManagerGetActiveAgentVersion:
    """Test get_active_agent_version parity with AgentVersionManager.get_active."""

    def test_returns_none_when_no_active_version(self, db: Database) -> None:
        """Agent with no active version returns None."""
        read_mgr = WorkspaceReadManager(db._engine)
        result = read_mgr.get_active_agent_version("nonexistent-agent")
        assert result is None

    def test_parity_with_source_manager(self, db: Database) -> None:
        """Read manager returns same row as source manager."""
        meta_mgr: AgentMetaManager = db.agent_meta
        version_mgr: AgentVersionManager = db.agent_versions
        read_mgr = WorkspaceReadManager(db._engine)

        agent_id = f"test-agent-{uuid.uuid4().hex[:8]}"
        now = now_iso()

        # Create agent metadata entry
        meta_mgr.insert(
            agent_id=agent_id,
            sync_mode="manual",
            export_to_disk=0,
            created_at=now,
            updated_at=now,
        )

        # Insert and activate a version
        version_mgr.insert_version(
            agent_id=agent_id,
            version=1,
            source_path="agents/test.toml",
            content_snapshot="snapshot",
            prompt_snapshot="prompt",
            content_hash="hash123",
            author="test",
            changelog="initial",
            is_legacy=0,
            created_at=now,
            activate_for=agent_id,
            activated_at=now,
        )

        source_result = version_mgr.get_active(agent_id)
        read_result = read_mgr.get_active_agent_version(agent_id)
        assert read_result == source_result


class TestWorkspaceReadManagerGetAgentDef:
    """Test get_agent_def parity with AgentDefManager.get."""

    def test_returns_none_for_missing_agent(self, db: Database) -> None:
        """Non-existent agent returns None."""
        read_mgr = WorkspaceReadManager(db._engine)
        result = read_mgr.get_agent_def("nonexistent-agent")
        assert result is None

    def test_returns_none_for_invalid_snapshot(self, db: Database) -> None:
        """Agent with invalid snapshot returns None."""
        meta_mgr: AgentMetaManager = db.agent_meta
        version_mgr: AgentVersionManager = db.agent_versions
        read_mgr = WorkspaceReadManager(db._engine)

        agent_id = f"test-agent-{uuid.uuid4().hex[:8]}"
        now = now_iso()

        meta_mgr.insert(
            agent_id=agent_id,
            sync_mode="manual",
            export_to_disk=0,
            created_at=now,
            updated_at=now,
        )

        # Use an invalid snapshot
        version_mgr.insert_version(
            agent_id=agent_id,
            version=1,
            source_path="agents/test.toml",
            content_snapshot="invalid yaml {{{",
            prompt_snapshot="test",
            content_hash="hash123",
            author="test",
            changelog="initial",
            is_legacy=0,
            created_at=now,
            activate_for=agent_id,
            activated_at=now,
        )

        result = read_mgr.get_agent_def(agent_id)
        # Invalid snapshot should return None
        assert result is None
