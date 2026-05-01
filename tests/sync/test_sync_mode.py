"""Test watcher respects agent_meta.sync_mode settings."""

from pathlib import Path

import pytest

from agentbox.core.data.store import SessionStore
from agentbox.core.definitions.loader import DefinitionLoader
from agentbox.core.sync.watcher import _process_changes


@pytest.fixture
def temp_store(tmp_path: Path) -> SessionStore:
    """Create a temporary SessionStore."""
    db_path = tmp_path / "test.db"
    store = SessionStore(db_path=db_path)
    return store


@pytest.fixture
def manifest_with_agent(tmp_path: Path) -> tuple[Path, str]:
    """Create a minimal test manifest with one agent."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    agent_dir = agents_dir / "test_agent"
    agent_dir.mkdir()

    agent_toml = agent_dir / "agent.toml"
    agent_toml.write_text(
        """id = "test_agent"
description = "Test agent"

[runner]
kind = "pydantic_ai"
"""
    )

    manifest = tmp_path / "agentbox.toml"
    manifest.write_text(
        f"""project = "test"
manifest_dir = "{agents_dir}"
"""
    )

    return tmp_path, "test_agent"


@pytest.mark.asyncio
async def test_watcher_skips_off_sync_mode(
    temp_store: SessionStore, manifest_with_agent: tuple[Path, str], tmp_path: Path
) -> None:
    """Verify watcher skips draft creation when sync_mode='off'."""
    project_root, agent_id = manifest_with_agent

    # Initialize loader
    loader = DefinitionLoader(
        project_root=project_root,
        manifest_path=project_root / "agentbox.toml",
        agents_bundle_dir=project_root / "agents",
    )

    # Load manifest and create v1 for the agent
    manifest = loader.load()
    agent = [a for a in manifest.agents if a.id == agent_id][0]

    # Create initial version
    v1 = temp_store.create_version(
        agent_id=agent_id,
        source_path=str(agent.source_path),
        source_format=agent.source_format.value if agent.source_format else "",
        content_snapshot='{"id":"test_agent"}',
        prompt_snapshot="",
        content_hash="abc123",
        author="test",
        changelog="initial",
    )
    temp_store.activate_version(agent_id, v1["id"])

    # Create agent_meta with sync_mode="off"
    temp_store.init_agent_meta(
        agent_id,
        sync_mode="off",
        export_to_disk=True,
        source_path=str(agent.source_path),
    )

    # Modify the agent file to trigger drift
    agent_file = agent.source_path
    agent_file.write_text(agent_file.read_text() + '\ndescription = "Modified"')

    # Process changes — should skip because sync_mode="off"
    await _process_changes(temp_store, loader, project_root)

    # Verify no new version was created
    versions = temp_store.list_versions(agent_id)
    assert len(versions) == 1  # Still just v1


@pytest.mark.asyncio
async def test_watcher_creates_draft_on_watch_sync_mode(
    temp_store: SessionStore, manifest_with_agent: tuple[Path, str]
) -> None:
    """Verify watcher creates draft when sync_mode='watch'."""
    project_root, agent_id = manifest_with_agent

    loader = DefinitionLoader(
        project_root=project_root,
        manifest_path=project_root / "agentbox.toml",
        agents_bundle_dir=project_root / "agents",
    )

    manifest = loader.load()
    agent = [a for a in manifest.agents if a.id == agent_id][0]

    # Create initial version
    v1 = temp_store.create_version(
        agent_id=agent_id,
        source_path=str(agent.source_path),
        source_format=agent.source_format.value if agent.source_format else "",
        content_snapshot='{"id":"test_agent"}',
        prompt_snapshot="",
        content_hash="abc123",
        author="test",
        changelog="initial",
    )
    temp_store.activate_version(agent_id, v1["id"])

    # Create agent_meta with sync_mode="watch"
    temp_store.init_agent_meta(
        agent_id,
        sync_mode="watch",
        export_to_disk=True,
        source_path=str(agent.source_path),
    )

    # Modify the agent file
    agent_file = agent.source_path
    agent_file.write_text(agent_file.read_text() + '\ndescription = "Modified"')

    # Process changes — should create draft
    await _process_changes(temp_store, loader, project_root)

    # Verify new draft version was created
    versions = temp_store.list_versions(agent_id)
    assert len(versions) == 2
    assert versions[0]["is_draft"] == 1  # Latest is draft
