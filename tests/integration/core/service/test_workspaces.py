"""Tests for ``core.service.workspaces``.

Pin the surface that REST + MCP both depend on: domain errors for
unknown names, path-escape rejection, registry CRUD round-trip,
permissions overlay shape, file ops, and list enrichment.

The mcp_manifest and config generator are heavy; tests pass
``mcp_manifest=None`` so derived ``allowed_tools`` falls back to ``[]``
and ``ConfigGenerator`` is exercised only via the by-name paths that
don't strictly need it. Where the generator would be invoked, we keep
the test scoped to inputs/error paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from agentbox.core.config import Settings
from agentbox.core.db.database import Database
from agentbox.core.service import workspaces as ws_service
from agentbox.core.service.workspaces import (
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
    WorkspaceService,
)


@dataclass(frozen=True)
class _FakeSettings:
    project_root: Path
    workspaces_root: Path


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    project_root = tmp_path / "project"
    project_root.mkdir()
    ws_root = project_root / "workspaces"
    ws_root.mkdir()
    # fake exposes only the two attrs the service reads; cast once here
    return cast(Settings, _FakeSettings(project_root=project_root, workspaces_root=ws_root))


# ---------------------------------------------------------------------------
# resolve_workspace_path
# ---------------------------------------------------------------------------


def test_resolve_workspace_path_raises_when_unknown(
    store: Database, settings: Settings
) -> None:
    with pytest.raises(WorkspaceNotFound):
        WorkspaceService().resolve_workspace_path(
            "missing", settings=settings
        )


def test_resolve_workspace_path_falls_back_to_workspaces_root(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    path, project_root = WorkspaceService().resolve_workspace_path(
        "alpha", settings=settings
    )
    assert path == settings.workspaces_root / "alpha"
    assert project_root == settings.project_root


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------


def test_create_workspace_registry_duplicate_raises(
    store: Database,
) -> None:

    svc = WorkspaceService()
    svc.create_workspace("alpha")
    with pytest.raises(WorkspaceExists):
        svc.create_workspace("alpha")


def test_delete_workspace_registry_raises_when_unknown(
    store: Database, settings: Settings
) -> None:
    with pytest.raises(WorkspaceNotFound):
        WorkspaceService().delete_workspace(
            "missing", settings=settings
        )


def test_delete_workspace_registry_purges_disk_when_requested(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    ws_path = settings.workspaces_root / "alpha"
    ws_path.mkdir()
    (ws_path / "file.txt").write_text("x")
    result = WorkspaceService().delete_workspace(
        "alpha",
        settings=settings,
        purge_disk=True,
    )
    assert result["deleted"] == "alpha"
    assert result["disk_removed"] is True
    assert not ws_path.exists()


# ---------------------------------------------------------------------------
# get_workspace_by_name + file enumeration
# ---------------------------------------------------------------------------


def test_get_workspace_by_name_lists_user_files(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    ws_path = settings.workspaces_root / "alpha"
    ws_path.mkdir()
    (ws_path / "user.txt").write_text("hi")
    (ws_path / ".claude").mkdir()
    (ws_path / ".claude" / "skip.txt").write_text("skip")
    (ws_path / "CLAUDE.md").write_text("render artifact")

    doc = WorkspaceService().get_workspace_by_name(
        "alpha", settings=settings
    )
    paths = {f["path"] for f in doc["files"]}
    assert "user.txt" in paths
    assert ".claude/skip.txt" not in paths
    assert "CLAUDE.md" not in paths


def test_is_user_file_excludes_render_artifacts_and_hidden_dirs() -> None:
    assert ws_service.is_user_file("notes.md") is True
    assert ws_service.is_user_file("CLAUDE.md") is False
    assert ws_service.is_user_file("AGENTS.md") is False
    assert ws_service.is_user_file(".claude/x") is False
    assert ws_service.is_user_file("permissions/capabilities.json") is False


# ---------------------------------------------------------------------------
# File ops + path-escape protection
# ---------------------------------------------------------------------------


def test_write_then_read_file_roundtrip(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    (settings.workspaces_root / "alpha").mkdir()
    written = WorkspaceService().write_workspace_file(
        "alpha",
        "notes/x.txt",
        "hi",
        settings=settings,
    )
    assert written == {"path": "notes/x.txt", "bytes": 2}
    read = WorkspaceService().read_workspace_file(
        "alpha", "notes/x.txt", settings=settings
    )
    assert read == {"path": "notes/x.txt", "content": "hi"}


def test_read_file_returns_none_for_missing(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    (settings.workspaces_root / "alpha").mkdir()
    assert (
        WorkspaceService().read_workspace_file(
            "alpha", "ghost.txt", settings=settings
        )
        is None
    )


def test_write_file_rejects_path_escape(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    (settings.workspaces_root / "alpha").mkdir()
    with pytest.raises(WorkspacePathEscape):
        WorkspaceService().write_workspace_file(
            "alpha",
            "../escape.txt",
            "evil",
            settings=settings,
        )


# ---------------------------------------------------------------------------
# Permissions overlay
# ---------------------------------------------------------------------------


def test_load_effective_permissions_returns_defaults_for_unknown_name(
    store: Database, settings: Settings
) -> None:
    perms = WorkspaceService().load_effective_permissions("")
    assert perms["allowed_tools"] == []
    assert perms["allow_file_write"] is True


def test_load_effective_permissions_applies_db_overlay(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha")
    ws_row = store.workspaces.get_by_name("alpha")
    assert ws_row is not None
    ws_id = ws_row["name"]  # workspace_id is the workspace name
    store.workspace_runtime_permissions.set_for_workspace(
        ws_id,
        allowed_builtin_tools=["WebFetch"],
        files=None,
        max_tokens=4096,
        allow_file_write=False,
        allow_network=False,
    )
    perms = WorkspaceService().load_effective_permissions("alpha")
    assert perms["allowed_builtin_tools"] == ["WebFetch"]
    assert perms["max_tokens"] == 4096
    assert perms["allow_file_write"] is False
    assert perms["allow_network"] is False


# ---------------------------------------------------------------------------
# list_workspaces_enriched
# ---------------------------------------------------------------------------


def test_list_workspaces_enriched_shape(
    store: Database, settings: Settings
) -> None:
    store.workspaces.insert(name="alpha", description="dev")
    (settings.workspaces_root / "alpha").mkdir()
    (settings.workspaces_root / "alpha" / "note.txt").write_text("hi")

    result = WorkspaceService().list_workspaces_enriched(
        settings=settings
    )
    assert len(result) == 1
    row = result[0]
    assert row["name"] == "alpha"
    assert row["kind"] == "named"
    assert row["file_count"] == 1
    assert row["exists"] is True
    assert row["on_disk"] is True
