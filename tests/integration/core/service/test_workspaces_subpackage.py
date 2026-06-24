"""Tests for the 6 workspaces subpackage split modules.

One happy-path + one error-path for each:
_registry, _configs, _files, _mcp, _permissions, _skills.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from agentbox.core.db import SessionStore
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
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "agentbox.sqlite")


@pytest.fixture
def settings(tmp_path: Path) -> _FakeSettings:
    project_root = tmp_path / "project"
    project_root.mkdir()
    ws_root = project_root / "workspaces"
    ws_root.mkdir()
    return _FakeSettings(project_root=project_root, workspaces_root=ws_root)


def _register(store: SessionStore, name: str) -> None:
    store.create_workspace(name)


# ── _registry ───────────────────────────────────────────────────────────


def test_create_workspace_registry_happy(store: SessionStore) -> None:
    result = create_workspace_registry("alpha", store=store)
    assert result["name"] == "alpha"


def test_create_workspace_registry_duplicate(store: SessionStore) -> None:
    _register(store, "alpha")
    with pytest.raises(WorkspaceExists):
        create_workspace_registry("alpha", store=store)


def test_delete_workspace_registry(store: SessionStore) -> None:
    _register(store, "alpha")
    delete_workspace_registry("alpha", store=store, settings=None)  # type: ignore[arg-type]
    with pytest.raises(WorkspaceNotFound):
        get_workspace_by_name("alpha", store=store, settings=None)  # type: ignore[arg-type]


def test_get_workspace_by_name_unknown(store: SessionStore, settings: _FakeSettings) -> None:
    with pytest.raises(WorkspaceNotFound):
        get_workspace_by_name("missing", store=store, settings=settings)  # type: ignore[arg-type]


def test_list_workspaces_enriched(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "ws1")
    _register(store, "ws2")
    result = list_workspaces_enriched(store=store, settings=settings)  # type: ignore[arg-type]
    assert len(result) >= 2


# ── _files ──────────────────────────────────────────────────────────────


def test_read_file_by_name_happy(
    store: SessionStore, settings: _FakeSettings
) -> None:
    _register(store, "filers")
    ws_path = settings.workspaces_root / "filers"
    ws_path.mkdir(parents=True, exist_ok=True)
    (ws_path / "README.md").write_text("hello")
    result = read_file_by_name(
        "filers", "README.md", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert result["content"] == "hello"


def test_write_file_then_read(
    store: SessionStore, settings: _FakeSettings
) -> None:
    _register(store, "writrs")
    write_file_by_name(
        "writrs", "notes.txt", "data", store=store, settings=settings  # type: ignore[arg-type]
    )
    result = read_file_by_name(
        "writrs", "notes.txt", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert result["content"] == "data"


def test_read_file_path_escape(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "escape")
    with pytest.raises(WorkspacePathEscape):
        read_file_by_name(
            "escape", "../outside.txt", store=store, settings=settings  # type: ignore[arg-type]
        )


# ── _permissions ────────────────────────────────────────────────────────


def test_get_permissions_defaults(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "perms-ws")
    result = get_permissions(
        "perms-ws", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert "permissions" in result


def test_set_permissions_happy(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "perms-ws2")
    result = set_permissions(
        "perms-ws2",
        {"network": "allow"},
        store=store,
        settings=settings,  # type: ignore[arg-type]
    )
    permissions = result.get("permissions", result)
    assert permissions is not None


def test_permissions_unknown_workspace(store: SessionStore, settings: _FakeSettings) -> None:
    with pytest.raises(WorkspaceNotFound):
        get_permissions(
            "missing", store=store, settings=settings  # type: ignore[arg-type]
        )


# ── _skills ─────────────────────────────────────────────────────────────


def test_generate_skills_by_name(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "skillz")
    result = generate_skills_by_name(
        "skillz", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
    assert result["workspace"] == "skillz"


def test_list_skills_by_name_empty(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "noskills")
    result = list_skills_by_name(
        "noskills", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
    assert result["skills"] == []


def test_get_skill_content_missing(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "nosuchskill")
    result = get_skill_content_by_name(
        "nosuchskill", "missing_skill", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert result is None


# ── _configs ────────────────────────────────────────────────────────────


def test_generate_configs_by_name(store: SessionStore, settings: _FakeSettings) -> None:
    _register(store, "cfgrs")
    result = generate_configs_by_name(
        "cfgrs", store=store, settings=settings  # type: ignore[arg-type]
    )
    assert isinstance(result, dict)
    # Generated config paths are nested under result["generated"]
    generated = result.get("generated", result)
    assert isinstance(generated, dict)
    assert len(generated) > 0


# ── _mcp ────────────────────────────────────────────────────────────────


def test_resolve_workspace_mcp_empty(store: SessionStore) -> None:
    result = resolve_workspace_mcp("nonexistent", store=store)
    assert isinstance(result, dict)
    assert "servers" in result


def test_resolve_workspace_mcp_with_workspace(store: SessionStore) -> None:
    store.create_workspace("mcp-ws")
    result = resolve_workspace_mcp("mcp-ws", store=store)
    assert isinstance(result, dict)
    assert "servers" in result
