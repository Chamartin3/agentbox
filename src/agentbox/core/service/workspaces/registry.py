"""Workspace registry CRUD: list / get / create / delete by name.

Delegates to ``WorkspaceService``. The ``store`` parameter is retained
for backward compatibility but workspace methods go through the service.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data import WorkspaceRow
from agentbox.core.db import SessionStore
from agentbox.core.resources.skills import discover_skills
from agentbox.core.service.workspaces.service import WorkspaceService

from .errors import WorkspaceExists, WorkspaceNotFound
from .files import is_user_file

__all__ = [
    "list_workspaces_enriched",
    "list_all_workspaces",
    "create_workspace_registry",
    "delete_workspace_registry",
    "get_workspace_by_name",
]


def _ws() -> WorkspaceService:
    return WorkspaceService()


def list_workspaces_enriched(
    *,
    store: SessionStore,
    settings: Settings,
) -> list[dict]:
    """Return all named workspaces with agent assignments + summary stats."""
    svc = _ws()
    registry = svc.list_workspaces(settings=settings)

    result: list[dict] = []
    for ws_row in registry:
        name = ws_row["name"]
        ws_path = Path(ws_row["path"])
        agents = []
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
                "resource_count": ws_row.get("resource_count", 0),
                "exists": ws_path.exists(),
                "on_disk": ws_row.get("on_disk", False),
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
) -> dict:
    svc = _ws()
    ws_path, _ = svc.resolve_workspace_path(name, settings=settings)
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
    """Return a WorkspaceInfo for every agent known to the DB."""
    from agentbox.core.workspaces.crud import info as _workspace_info  # noqa: PLC0415
    from agentbox.core.service.agents import list_all_agents  # noqa: PLC0415
    return [_workspace_info(a, settings, store) for a in list_all_agents(store=store)]
