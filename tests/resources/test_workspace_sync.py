"""Phase 1: sync_workspace orchestrator — env-doc + subagents + provenance."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox.core.data.store import SessionStore
from agentbox.core.workspace.sync import sync_workspace, sync_workspace_by_name


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "db.sqlite")


@pytest.fixture
def fake_settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_root=tmp_path,
        workspaces_root=tmp_path / "workspaces",
        resource_cache_dir=tmp_path / "cache",
    )


def _seed_workspace(store: SessionStore, name: str) -> None:
    store.upsert_workspace(name, path=f"workdir/{name}", source="db")


def _save_env_doc(store: SessionStore, workspace_id: str) -> None:
    content = {
        "project_name": "test",
        "overview": "test workspace",
        "conventions": [],
        "commands": [],
        "sections": [],
    }
    store.save_env_doc(workspace_id, content, changelog="seed", publish=True)


def test_sync_writes_env_doc_files_and_provenance(
    store: SessionStore, fake_settings, tmp_path: Path
) -> None:
    _seed_workspace(store, "default")
    _save_env_doc(store, "default")
    workdir = tmp_path / "workdir" / "default"

    result = sync_workspace(store, fake_settings, "default", workdir)

    assert (workdir / "CLAUDE.md").exists()
    assert (workdir / "AGENTS.md").exists()
    meta = json.loads((workdir / ".agentbox" / "meta.json").read_text())
    assert meta["workspace_id"] == "default"
    assert set(meta["env_doc_files"]) == {"CLAUDE.md", "AGENTS.md"}
    assert result.errors == []


def test_sync_skips_ephemeral(
    store: SessionStore, fake_settings, tmp_path: Path
) -> None:
    workdir = tmp_path / "tmpws"
    result = sync_workspace(store, fake_settings, "<ephemeral>", workdir)
    assert result.env_doc_files == []
    assert not (workdir / "CLAUDE.md").exists()


def test_sync_no_env_doc_still_writes_provenance(
    store: SessionStore, fake_settings, tmp_path: Path
) -> None:
    """A workspace with no env-doc gets no CLAUDE.md but still gets meta.json."""
    _seed_workspace(store, "barebones")
    workdir = tmp_path / "workdir" / "barebones"

    result = sync_workspace(store, fake_settings, "barebones", workdir)

    assert result.env_doc_files == []
    assert not (workdir / "CLAUDE.md").exists()
    assert (workdir / ".agentbox" / "meta.json").exists()


def test_sync_workspace_by_name_resolves_path(
    store: SessionStore, fake_settings, tmp_path: Path
) -> None:
    """The convenience wrapper resolves workspace_id → workdir from the DB."""
    _seed_workspace(store, "named")
    _save_env_doc(store, "named")

    result = sync_workspace_by_name(store, fake_settings, "named")

    assert result is not None
    assert result.workdir == (tmp_path / "workdir" / "named").resolve()
    assert (tmp_path / "workdir" / "named" / "CLAUDE.md").exists()


def test_sync_workspace_by_name_unknown_returns_none(
    store: SessionStore, fake_settings
) -> None:
    assert sync_workspace_by_name(store, fake_settings, "ghost") is None


# ---------------------------------------------------------------------------
# Orphan cleanup
# ---------------------------------------------------------------------------


def test_sync_removes_orphans_recorded_in_previous_meta(
    store: SessionStore, fake_settings, tmp_path: Path
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

    result = sync_workspace(store, fake_settings, "ws", workdir)

    assert set(result.orphans_removed) == {"old-folder", "old-doc.md"}
    assert not (workdir / "old-folder").exists()
    assert not (workdir / "old-doc.md").exists()


def test_sync_does_not_remove_files_outside_previous_meta(
    store: SessionStore, fake_settings, tmp_path: Path
) -> None:
    """Files agentbox never materialized are sacred — never auto-deleted."""
    _seed_workspace(store, "ws2")
    workdir = tmp_path / "workdir" / "ws2"
    workdir.mkdir(parents=True)
    (workdir / "user-handwritten.md").write_text("mine")
    # No prior meta.json → no orphans should be removed.

    result = sync_workspace(store, fake_settings, "ws2", workdir)

    assert result.orphans_removed == []
    assert (workdir / "user-handwritten.md").exists()
