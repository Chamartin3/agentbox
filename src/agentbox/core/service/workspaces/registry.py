"""Workspace registry CRUD: list / get / create / delete by name."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from agentbox.config import Settings
from agentbox.core.data import SessionStore, WorkspaceRow
from agentbox.core.resources.skills import discover_skills
from agentbox.core.service.agents import list_all_agents
from agentbox.core.workspaces.crud import info as _workspace_info

from .errors import WorkspaceExists, WorkspaceNotFound
from .files import is_user_file, resolve_workspace_path

__all__ = [
    "list_workspaces_enriched",
    "list_all_workspaces",
    "create_workspace_registry",
    "delete_workspace_registry",
    "get_workspace_by_name",
]


def list_workspaces_enriched(
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> list[dict]:
    """Return all named workspaces with agent assignments + summary stats."""
    try:
        manifest = loader.load() if loader is not None else None
    except Exception:
        manifest = None

    registry = store.list_workspaces()
    ws_root = settings.workspaces_root
    disk_ids: set[str] = set()
    if ws_root.exists():
        disk_ids = {
            p.name
            for p in ws_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        }

    workspace_agents: dict[str, list[str]] = {}
    if manifest:
        for a in manifest.agents:
            ws_name = a.workspace or "default"
            workspace_agents.setdefault(ws_name, []).append(a.id)

    try:
        resource_counts = store.count_workspace_file_bindings_by_workspace()
    except Exception:
        resource_counts = {}

    result: list[dict] = []
    for ws_row in registry:
        name = ws_row["name"]
        rel_path = ws_row.get("path")
        ws_path = (
            settings.project_root / rel_path
            if rel_path
            else ws_root / name
        )
        agents = workspace_agents.get(name, [])
        file_count = 0
        skill_count = 0
        if ws_path.exists():
            for p in ws_path.rglob("*"):
                if p.is_file() and is_user_file(str(p.relative_to(ws_path))):
                    file_count += 1
            skill_count = len(discover_skills(ws_path))
        result.append(
            {
                "name": name,
                "path": str(ws_path),
                "description": ws_row.get("description"),
                "source": ws_row.get("source"),
                "kind": "named",
                "agents": agents,
                "agent_count": len(agents),
                "file_count": file_count,
                "skill_count": skill_count,
                "resource_count": resource_counts.get(name, 0),
                "exists": ws_path.exists(),
                "on_disk": name in disk_ids,
                "created_at": ws_row.get("created_at"),
                "updated_at": ws_row.get("updated_at"),
            }
        )
    return result


def create_workspace_registry(
    name: str,
    *,
    store: SessionStore,
    description: str | None = None,
    path: str | None = None,
) -> WorkspaceRow:
    try:
        return store.create_workspace(name, description=description, path=path)
    except ValueError as exc:
        raise WorkspaceExists(name, str(exc)) from exc


def delete_workspace_registry(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    purge_disk: bool = False,
) -> dict:
    existing = store.get_workspace(name)
    if existing is None:
        raise WorkspaceNotFound(name)
    counts = store.delete_workspace_cascade(name)
    disk_removed = False
    if purge_disk:
        existing_path = existing.get("path")
        ws_path: Path
        if existing_path:
            ws_path = settings.project_root / existing_path
        else:
            ws_path = settings.workspaces_root / name
        if ws_path.exists() and ws_path.is_dir():
            shutil.rmtree(ws_path)
            disk_removed = True
    return {"deleted": name, "counts": counts, "disk_removed": disk_removed}


def get_workspace_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
) -> dict:
    ws_path, _ = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    files: list[dict] = []
    if ws_path.exists():
        for p in sorted(ws_path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(ws_path))
                if not is_user_file(rel):
                    continue
                files.append({"path": rel, "size": p.stat().st_size})
    return {
        "name": name,
        "path": str(ws_path),
        "exists": ws_path.exists(),
        "files": files,
        "generated_configs": {},
    }


def list_all_workspaces(
    *,
    store: SessionStore,
    settings: Settings,
) -> list:
    """Return a WorkspaceInfo for every agent known to the DB.

    This was moved from ``core.workspaces.manager.list_all`` to the
    service layer to fix the R4 violation (domain importing upward
    into service).
    """
    return [
        _workspace_info(a, settings, store)
        for a in list_all_agents(store=store)
    ]
