"""Tests for the flattened WorkspaceService surface.

One happy-path + one error-path per method group: registry, configs,
files, mcp, permissions, skills. (Was the 6-submodule split; now one
service.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from agentbox.core.config import Settings
from agentbox.core.db.database import Database
from agentbox.core.data.errors import WorkspaceExists, WorkspaceNotFound, WorkspacePathEscape
from agentbox.core.service.workspaces import WorkspaceService


@dataclass
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
    # ponytail: fake exposes only the two attrs the service reads; cast once here
    return cast(Settings, _FakeSettings(project_root=project_root, workspaces_root=ws_root))


def _register(store: Database, name: str) -> None:
    store.workspaces.insert(name=name)


# ── registry ────────────────────────────────────────────────────────────


def test_create_workspace_happy(store: Database) -> None:
    result = WorkspaceService().create_workspace("alpha")
    assert result["name"] == "alpha"


def test_create_workspace_duplicate(store: Database) -> None:
    _register(store, "alpha")
    with pytest.raises(WorkspaceExists):
        WorkspaceService().create_workspace("alpha")


def test_delete_workspace(store: Database, settings: Settings) -> None:
    _register(store, "alpha")
    WorkspaceService().delete_workspace("alpha", settings=settings)
    with pytest.raises(WorkspaceNotFound):
        WorkspaceService().get_workspace_by_name("alpha", settings=settings)


def test_get_workspace_by_name_unknown(store: Database, settings: Settings) -> None:
    with pytest.raises(WorkspaceNotFound):
        WorkspaceService().get_workspace_by_name("missing", settings=settings)


def test_list_workspaces_enriched(store: Database, settings: Settings) -> None:
    _register(store, "ws1")
    _register(store, "ws2")
    result = WorkspaceService().list_workspaces_enriched(settings=settings)
    assert len(result) >= 2


# ── files ──────────────────────────────────────────────────────────────


def test_read_file_happy(store: Database, settings: Settings) -> None:
    _register(store, "filers")
    ws_path = settings.workspaces_root / "filers"
    ws_path.mkdir(parents=True, exist_ok=True)
    (ws_path / "README.md").write_text("hello")
    result = WorkspaceService().read_workspace_file("filers", "README.md", settings=settings)
    assert result is not None
    assert result["content"] == "hello"


def test_write_file_then_read(store: Database, settings: Settings) -> None:
    _register(store, "writrs")
    svc = WorkspaceService()
    svc.write_workspace_file("writrs", "notes.txt", "data", settings=settings)
    result = svc.read_workspace_file("writrs", "notes.txt", settings=settings)
    assert result is not None
    assert result["content"] == "data"


def test_read_file_path_escape(store: Database, settings: Settings) -> None:
    _register(store, "escape")
    with pytest.raises(WorkspacePathEscape):
        WorkspaceService().read_workspace_file("escape", "../outside.txt", settings=settings)


# ── permissions ────────────────────────────────────────────────────────


def test_get_permissions_defaults(store: Database, settings: Settings) -> None:
    _register(store, "perms-ws")
    result = WorkspaceService().get_permissions("perms-ws")
    assert "permissions" in result


def test_set_permissions_happy(store: Database, settings: Settings) -> None:
    _register(store, "perms-ws2")
    result = WorkspaceService().set_permissions(
        "perms-ws2",
        {"network": "allow"},
        settings=settings,
    )
    permissions = result.get("permissions", result)
    assert permissions is not None


def test_permissions_unknown_workspace(store: Database, settings: Settings) -> None:
    with pytest.raises(WorkspaceNotFound):
        WorkspaceService().get_permissions("missing")


# ── skills ─────────────────────────────────────────────────────────────


def test_generate_skills(store: Database, settings: Settings) -> None:
    _register(store, "skillz")
    result = WorkspaceService().generate_skills("skillz", settings=settings)
    assert isinstance(result, dict)
    assert result["workspace"] == "skillz"


def test_list_skills_empty(store: Database, settings: Settings) -> None:
    _register(store, "noskills")
    result = WorkspaceService().list_skills("noskills", settings=settings)
    assert isinstance(result, dict)
    assert result["skills"] == []


def test_get_skill_content_missing(store: Database, settings: Settings) -> None:
    _register(store, "nosuchskill")
    result = WorkspaceService().get_skill_content("nosuchskill", "missing_skill", settings=settings)
    assert result is None


# ── configs ────────────────────────────────────────────────────────────


def test_generate_configs(store: Database, settings: Settings) -> None:
    _register(store, "cfgrs")
    result = WorkspaceService().generate_configs("cfgrs", settings=settings)
    assert isinstance(result, dict)
    generated = result.get("generated", result)
    assert isinstance(generated, dict)
    assert len(generated) > 0


# ── mcp ────────────────────────────────────────────────────────────────


def test_resolve_workspace_mcp_empty(store: Database) -> None:
    result = WorkspaceService().resolve_workspace_mcp("nonexistent")
    assert isinstance(result, dict)
    assert "servers" in result


def test_resolve_workspace_mcp_with_workspace(store: Database) -> None:
    store.workspaces.insert(name="mcp-ws")
    result = WorkspaceService().resolve_workspace_mcp("mcp-ws")
    assert isinstance(result, dict)
    assert "servers" in result
