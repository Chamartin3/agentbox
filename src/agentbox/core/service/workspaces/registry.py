"""Workspace registry CRUD: list / get / create / delete by name.

Delegates to ``WorkspaceService``. The ``store`` parameter has been removed
— all workspace operations go through the service or its managers.
"""

from __future__ import annotations

from agentbox.core.data.payload_types import WorkspaceDeleteResult, WorkspaceDetail, WorkspaceFileInfo, WorkspaceListItem

from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core.data import AgentDef
from agentbox.core.data.rows import WorkspaceRow
from agentbox.core.db.database import get_database
from agentbox.core.resources.skills import discover_skills
from agentbox.core.service.workspaces.service import WorkspaceService
from agentbox.core.workspaces.workdir import info as _workspace_info

from agentbox.core.data.errors import WorkspaceExists
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
    settings: Settings,
) -> list[WorkspaceListItem]:
    """Return all named workspaces with agent assignments + summary stats."""
    svc = _ws()
    registry = svc.list_workspaces(settings=settings)

    result: list[WorkspaceListItem] = []
    for ws_row in registry:
        name = ws_row["name"]
        ws_path = Path(ws_row["path"])
        agents: list[str] = []
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
    description: str | None = None,
    path: str | None = None,
) -> WorkspaceRow:
    try:
        return _ws().create_workspace(name, description=description, path=path)
    except Exception as exc:
        raise WorkspaceExists(name, str(exc)) from exc


def delete_workspace_registry(
    name: str,
    *,
    settings: Settings,
    purge_disk: bool = False,
) -> WorkspaceDeleteResult:
    return _ws().delete_workspace(name, settings=settings, purge_disk=purge_disk)


def get_workspace_by_name(
    name: str,
    *,
    settings: Settings,
) -> WorkspaceDetail:
    svc = _ws()
    ws_path, _ = svc.resolve_workspace_path(name, settings=settings)
    files: list[WorkspaceFileInfo] = []
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
    settings: Settings,
) -> list:
    """Return a WorkspaceInfo for every agent known to the DB.

    workspace path DB lookup is skipped (store=None) — deprecated callers
    should use WorkspaceService.list_workspaces() instead.
    """
    db = get_database(str(settings.db_path))
    agents: list[AgentDef] = []
    for r in db.agent_versions.list_latest_per_agent():
        try:
            agents.append(AgentDef.from_db_row(r))
        except Exception:
            pass
    return [_workspace_info(a, settings, None) for a in agents]
