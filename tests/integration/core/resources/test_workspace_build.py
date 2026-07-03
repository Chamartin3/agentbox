"""Phase 1: build_workspace orchestrator — env-doc + subagents + provenance."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from agentbox.core.config import Settings

import pytest
from agentbox.core.db.database import Database
from agentbox.core.workspaces.build import build_workspace, build_workspace_by_name


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


@pytest.fixture
def fake_settings(tmp_path: Path) -> Settings:
    return cast(Settings, SimpleNamespace(
        project_root=tmp_path,
        workspaces_root=tmp_path / "workspaces",
        resource_cache_dir=tmp_path / "cache",
    ))


def _build_workspace_from_store(
    store: Database, settings: Settings, workspace_id: str, workdir: Path
):
    """Helper to extract managers from store and call build_workspace."""
    return build_workspace(
        store.workspaces,
        store.agent_defs,
        store.workspace_subagents,
        store.agent_versions,
        store.workspace_file_resource_bindings,
        store.resources,
        store.resource_versions,
        store.resource_blobs,
        store.workspace_mcp_overrides,
        store.workspace_mcp_tool_overrides,
        store.workspace_env_doc_versions,
        settings,
        workspace_id,
        workdir,
    )


def _build_workspace_by_name_from_store(
    store: Database, settings: Settings, workspace_id: str
):
    """Helper to extract managers from store and call build_workspace_by_name."""
    return build_workspace_by_name(
        store.workspaces,
        store.agent_defs,
        store.workspace_subagents,
        store.agent_versions,
        store.workspace_file_resource_bindings,
        store.resources,
        store.resource_versions,
        store.resource_blobs,
        store.workspace_mcp_overrides,
        store.workspace_mcp_tool_overrides,
        store.workspace_env_doc_versions,
        settings,
        workspace_id,
    )


def _seed_workspace(store: Database, name: str) -> None:
    store.workspaces.upsert(name, path=f"workdir/{name}", source="db")


def _save_env_doc(store: Database, workspace_id: str) -> None:
    content = {
        "project_name": "test",
        "overview": "test workspace",
        "conventions": [],
        "commands": [],
        "sections": [],
    }
    store.workspace_env_doc_versions.save(workspace_id, content, changelog="seed", publish=True)


def test_sync_writes_env_doc_files_and_provenance(
    store: Database, fake_settings, tmp_path: Path
) -> None:
    _seed_workspace(store, "default")
    _save_env_doc(store, "default")
    workdir = tmp_path / "workdir" / "default"

    result = _build_workspace_from_store(store, fake_settings, "default", workdir)

    assert (workdir / "CLAUDE.md").exists()
    assert (workdir / "AGENTS.md").exists()
    meta = json.loads((workdir / ".agentbox" / "meta.json").read_text())
    assert meta["workspace_id"] == "default"
    assert set(meta["env_doc_files"]) == {"CLAUDE.md", "AGENTS.md"}
    assert result.errors == []


def test_sync_skips_ephemeral(
    store: Database, fake_settings, tmp_path: Path
) -> None:
    workdir = tmp_path / "tmpws"
    result = _build_workspace_from_store(store, fake_settings, "<ephemeral>", workdir)
    assert result.env_doc_files == []
    assert not (workdir / "CLAUDE.md").exists()


def test_sync_no_env_doc_still_writes_provenance(
    store: Database, fake_settings, tmp_path: Path
) -> None:
    """A workspace with no env-doc gets no CLAUDE.md but still gets meta.json."""
    _seed_workspace(store, "barebones")
    workdir = tmp_path / "workdir" / "barebones"

    result = _build_workspace_from_store(store, fake_settings, "barebones", workdir)

    assert result.env_doc_files == []
    assert not (workdir / "CLAUDE.md").exists()
    assert (workdir / ".agentbox" / "meta.json").exists()


def test_build_workspace_by_name_resolves_path(
    store: Database, fake_settings, tmp_path: Path
) -> None:
    """The convenience wrapper resolves workspace_id → workdir from the DB."""
    _seed_workspace(store, "named")
    _save_env_doc(store, "named")

    result = _build_workspace_by_name_from_store(store, fake_settings, "named")

    assert result is not None
    assert result.workdir == (tmp_path / "workdir" / "named").resolve()
    assert (tmp_path / "workdir" / "named" / "CLAUDE.md").exists()


def test_build_workspace_by_name_unknown_returns_none(
    store: Database, fake_settings
) -> None:
    assert _build_workspace_by_name_from_store(store, fake_settings, "ghost") is None


# ---------------------------------------------------------------------------
# Orphan cleanup
# ---------------------------------------------------------------------------


def test_sync_removes_orphans_recorded_in_previous_meta(
    store: Database, fake_settings, tmp_path: Path
) -> None:
    """A path materialized last time but not this time should be removed."""
    _seed_workspace(store, "ws")
    workdir = tmp_path / "workdir" / "ws"
    workdir.mkdir(parents=True)
    # Simulate previous sync produced 'old-folder' and 'old-doc.md'
    (workdir / "old-folder").mkdir()
    (workdir / "old-folder" / "inner.txt").write_text("hi")
    (workdir / "old-doc.md").write_text("old")
    (workdir / ".agentbox").mkdir()
    (workdir / ".agentbox" / "meta.json").write_text(
        json.dumps(
            {
                "workspace_id": "ws",
                "materialized_paths": ["old-folder", "old-doc.md"],
            }
        )
    )

    result = _build_workspace_from_store(store, fake_settings, "ws", workdir)

    assert set(result.orphans_removed) == {"old-folder", "old-doc.md"}
    assert not (workdir / "old-folder").exists()
    assert not (workdir / "old-doc.md").exists()


def test_sync_does_not_remove_files_outside_previous_meta(
    store: Database, fake_settings, tmp_path: Path
) -> None:
    """Files agentbox never materialized are sacred — never auto-deleted."""
    _seed_workspace(store, "ws2")
    workdir = tmp_path / "workdir" / "ws2"
    workdir.mkdir(parents=True)
    (workdir / "user-handwritten.md").write_text("mine")
    # No prior meta.json → no orphans should be removed.

    result = _build_workspace_from_store(store, fake_settings, "ws2", workdir)

    assert result.orphans_removed == []
    assert (workdir / "user-handwritten.md").exists()
