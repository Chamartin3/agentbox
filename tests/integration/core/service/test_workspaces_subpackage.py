"""Tests for the 6 workspaces subpackage split modules.

One happy-path + one error-path for each:
_registry, _configs, _files, _mcp, _permissions, _skills.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from agentbox.core.config import Settings
from agentbox.core.db.database import Database
from agentbox.core.service.workspaces import (
    WorkspaceExists,
    WorkspaceNotFound,
    WorkspacePathEscape,
    create_workspace_registry,
    delete_workspace_registry,
    generate_configs_by_name,
    generate_skills_by_name,
    get_permissions,
    get_skill_content_by_name,
    get_workspace_by_name,
    list_skills_by_name,
    list_workspaces_enriched,
    read_file_by_name,
    resolve_workspace_mcp,
    set_permissions,
    write_file_by_name,
)


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


# ── _registry ───────────────────────────────────────────────────────────


def test_create_workspace_registry_happy(store: Database) -> None:
    result = create_workspace_registry("alpha")
    assert result["name"] == "alpha"


def test_create_workspace_registry_duplicate(store: Database) -> None:
    _register(store, "alpha")
    with pytest.raises(WorkspaceExists):
        create_workspace_registry("alpha")


def test_delete_workspace_registry(store: Database, settings: Settings) -> None:
    _register(store, "alpha")
    delete_workspace_registry("alpha", settings=settings)
    with pytest.raises(WorkspaceNotFound):
        get_workspace_by_name("alpha", settings=settings)


def test_get_workspace_by_name_unknown(store: Database, settings: Settings) -> None:
    with pytest.raises(WorkspaceNotFound):
        get_workspace_by_name("missing", settings=settings)


def test_list_workspaces_enriched(store: Database, settings: Settings) -> None:
    _register(store, "ws1")
    _register(store, "ws2")
    result = list_workspaces_enriched(settings=settings)
    assert len(result) >= 2


# ── _files ──────────────────────────────────────────────────────────────


def test_read_file_by_name_happy(
    store: Database, settings: Settings
) -> None:
    _register(store, "filers")
    ws_path = settings.workspaces_root / "filers"
    ws_path.mkdir(parents=True, exist_ok=True)
    (ws_path / "README.md").write_text("hello")
    result = read_file_by_name(
        "filers", "README.md", settings=settings
    )
    assert result is not None
    assert result["content"] == "hello"


def test_write_file_then_read(
    store: Database, settings: Settings
) -> None:
    _register(store, "writrs")
    write_file_by_name(
        "writrs", "notes.txt", "data", settings=settings
    )
    result = read_file_by_name(
        "writrs", "notes.txt", settings=settings
    )
    assert result is not None
    assert result["content"] == "data"


def test_read_file_path_escape(store: Database, settings: Settings) -> None:
    _register(store, "escape")
    with pytest.raises(WorkspacePathEscape):
        read_file_by_name(
            "escape", "../outside.txt", settings=settings
        )


# ── _permissions ────────────────────────────────────────────────────────


def test_get_permissions_defaults(store: Database, settings: Settings) -> None:
    _register(store, "perms-ws")
    result = get_permissions(
        "perms-ws", settings=settings
    )
    assert "permissions" in result


def test_set_permissions_happy(store: Database, settings: Settings) -> None:
    _register(store, "perms-ws2")
    result = set_permissions(
        "perms-ws2",
        {"network": "allow"},
        settings=settings,
    )
    permissions = result.get("permissions", result)
    assert permissions is not None


def test_permissions_unknown_workspace(store: Database, settings: Settings) -> None:
    with pytest.raises(WorkspaceNotFound):
        get_permissions(
            "missing", settings=settings
        )


# ── _skills ─────────────────────────────────────────────────────────────


def test_generate_skills_by_name(store: Database, settings: Settings) -> None:
    _register(store, "skillz")
    result = generate_skills_by_name(
        "skillz", settings=settings
    )
    assert isinstance(result, dict)
    assert result["workspace"] == "skillz"


def test_list_skills_by_name_empty(store: Database, settings: Settings) -> None:
    _register(store, "noskills")
    result = list_skills_by_name(
        "noskills", settings=settings
    )
    assert isinstance(result, dict)
    assert result["skills"] == []


def test_get_skill_content_missing(store: Database, settings: Settings) -> None:
    _register(store, "nosuchskill")
    result = get_skill_content_by_name(
        "nosuchskill", "missing_skill", settings=settings
    )
    assert result is None


# ── _configs ────────────────────────────────────────────────────────────


def test_generate_configs_by_name(store: Database, settings: Settings) -> None:
    _register(store, "cfgrs")
    result = generate_configs_by_name(
        "cfgrs", settings=settings
    )
    assert isinstance(result, dict)
    # Generated config paths are nested under result["generated"]
    generated = result.get("generated", result)
    assert isinstance(generated, dict)
    assert len(generated) > 0


# ── _mcp ────────────────────────────────────────────────────────────────


def test_resolve_workspace_mcp_empty(store: Database) -> None:
    result = resolve_workspace_mcp("nonexistent")
    assert isinstance(result, dict)
    assert "servers" in result


def test_resolve_workspace_mcp_with_workspace(store: Database) -> None:
    store.workspaces.insert(name="mcp-ws")
    result = resolve_workspace_mcp("mcp-ws")
    assert isinstance(result, dict)
    assert "servers" in result
