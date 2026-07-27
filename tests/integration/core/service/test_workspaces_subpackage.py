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
    # fake exposes only the two attrs the service reads; cast once here
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


def test_refresh_workspace_mcp_cache_deletes_only_existing(store: Database) -> None:
    from agentbox.core.config import load_settings

    svc = WorkspaceService()
    store.workspaces.insert(name="mcp-ws")
    svc.set_mcp_server_override("mcp-ws", "srv-a", enabled=True, changelog="add a")
    svc.set_mcp_server_override("mcp-ws", "srv-b", enabled=True, changelog="add b")

    # srv-a has an on-disk cache file, srv-b does not.
    cache_dir = load_settings().mcp_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "srv-a.json").write_text("{}", encoding="utf-8")

    statuses = svc.refresh_workspace_mcp_cache("mcp-ws")

    by_name = {s["name"]: s["invalidated"] for s in statuses}
    assert by_name["srv-a"] is True and by_name["srv-b"] is False
    assert not (cache_dir / "srv-a.json").exists()  # the present cache was removed


# ── resolve_launch_target ──────────────────────────────────────────────────


def test_resolve_launch_target_ephemeral_flag(store: Database, tmp_path: Path) -> None:
    """ephemeral=True → tmp dir that exists, is_ephemeral=True, creds/name=None."""
    import shutil

    from agentbox.core.service.workspaces import WorkspaceService

    target = WorkspaceService().resolve_launch_target(None, None, ephemeral=True)
    assert target["is_ephemeral"] is True
    assert target["path"].is_dir()
    assert target["creds"] is None
    assert target["name"] is None
    # Cleanup the tmp dir we created
    shutil.rmtree(target["path"], ignore_errors=True)


def test_resolve_launch_target_named_db_workspace(
    store: Database, settings: Settings
) -> None:
    """Named DB workspace → its resolved path, is_ephemeral=False, name set."""
    store.workspaces.insert(name="launch-ws")
    from agentbox.core.service.workspaces import WorkspaceService

    target = WorkspaceService().resolve_launch_target(
        None, "launch-ws", ephemeral=False, settings=settings
    )
    assert target["is_ephemeral"] is False
    assert target["name"] == "launch-ws"
    assert target["creds"] is None
    assert target["path"].is_dir()


def test_resolve_launch_target_explicit_path_override(
    store: Database, settings: Settings
) -> None:
    """Explicit workspace path override not in DB → path, name=None."""
    from agentbox.core.service.workspaces import WorkspaceService

    # "nonexistent-override" is not in the DB, so it's an explicit-path override.
    target = WorkspaceService().resolve_launch_target(
        None, "nonexistent-override", ephemeral=False, settings=settings
    )
    assert target["is_ephemeral"] is False
    assert target["name"] is None  # no registry name
    assert target["path"].is_dir()


def test_resolve_launch_target_unresolved_raises(store: Database) -> None:
    """Nothing provided → LaunchTargetUnresolved with the canonical message."""
    from agentbox.core.data.errors import LaunchTargetUnresolved
    from agentbox.core.service.workspaces import WorkspaceService

    with pytest.raises(LaunchTargetUnresolved) as exc_info:
        WorkspaceService().resolve_launch_target(None, None, ephemeral=False)

    msg = str(exc_info.value)
    assert "No workspace specified" in msg
    assert "agentbox ws ls" in msg


def test_resolve_launch_target_agent_ephemeral_workspace(store: Database) -> None:
    """Agent with workspace='<ephemeral>' → tmp dir + is_ephemeral=True."""
    import shutil

    from agentbox.core.data.agent_defs import AgentDef
    from agentbox.core.service.workspaces import WorkspaceService

    agent_def = AgentDef(id="test-agent", workspace="<ephemeral>")
    target = WorkspaceService().resolve_launch_target(agent_def, None, ephemeral=False)
    assert target["is_ephemeral"] is True
    assert target["name"] is None
    shutil.rmtree(target["path"], ignore_errors=True)


# ── resolve_launch_mcp_servers ────────────────────────────────────────────


def test_resolve_launch_mcp_servers_no_workspace(store: Database) -> None:
    """None or empty workspace_id → empty list (no MCP servers to resolve)."""
    svc = WorkspaceService()
    assert svc.resolve_launch_mcp_servers(None) == []
    assert svc.resolve_launch_mcp_servers("") == []


def test_resolve_launch_mcp_servers_unknown_workspace_returns_empty(
    store: Database,
) -> None:
    """An unregistered workspace_id yields [] (no project MCP servers in test)."""
    result = WorkspaceService().resolve_launch_mcp_servers("no-such-ws")
    assert result == []


def test_resolve_launch_mcp_servers_filters_disabled_and_no_endpoint(
    store: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only enabled servers with a url or command survive the filter."""
    from agentbox.core.data.workspace_defs import McpServerSpec
    from agentbox.core.service.workspaces import WorkspaceService
    from agentbox.core.service.system import SystemService

    store.workspaces.insert(name="filter-ws")
    svc = WorkspaceService()

    # Stub get_project_mcp_servers so we control the server set without
    # touching the real project config.  Two servers:
    #   - enabled-url  : enabled, has url → should appear
    #   - disabled-cmd : disabled, has command → should NOT appear
    fake_specs = [
        McpServerSpec(name="enabled-url", url="http://mcp.example.com", transport="http"),
        McpServerSpec(name="disabled-cmd", command=["npx", "mcp-server"], transport="stdio"),
    ]
    monkeypatch.setattr(SystemService, "get_project_mcp_servers", lambda self: fake_specs)

    # Override: disabled-cmd → explicitly disabled.
    svc.set_mcp_server_override("filter-ws", "disabled-cmd", enabled=False, changelog="disable")
    # Default policy is deny-unless-enabled, so we explicitly enable the url server.
    svc.set_mcp_server_override("filter-ws", "enabled-url", enabled=True, changelog="enable")

    result = svc.resolve_launch_mcp_servers("filter-ws")

    names = [s["name"] for s in result]
    assert "enabled-url" in names, "server with url must appear"
    assert "disabled-cmd" not in names, "disabled server must be excluded"

    # Verify the shape of the returned entry.
    [entry] = [s for s in result if s["name"] == "enabled-url"]
    assert entry["url"] == "http://mcp.example.com"
    assert entry["transport"] == "http"
    assert entry["command"] is None
