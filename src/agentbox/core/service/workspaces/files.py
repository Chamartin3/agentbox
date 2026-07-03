"""Workspace file IO, path resolution, and the ``is_user_file`` filter.

Delegates path resolution to ``WorkspaceService``. File read/write
operations route through the service.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.service.agents.prompts import AgentNotFound
from agentbox.core.service.workspaces.service import WorkspaceService

from .errors import WorkspacePathEscape

if TYPE_CHECKING:
    from agentbox.core.db import AgentDefManager

__all__ = [
    "is_user_file",
    "resolve_workspace_path",
    "read_file_by_name",
    "write_file_by_name",
    "get_workspace_for_agent",
    "create_workspace_for_agent",
    "reset_workspace_for_agent",
    "read_file_for_agent",
    "write_file_for_agent",
]


def _ws() -> WorkspaceService:
    return WorkspaceService()


def _resolve_agent_or_raise(agent_id: str, *, agent_defs: AgentDefManager):
    agent = agent_defs.get(agent_id)
    if agent is None:
        raise AgentNotFound(agent_id)
    return agent


_FILE_HIDE_PREFIXES = (
    ".agentbox/",
    ".claude/",
    ".opencode/",
    "permissions/",
    "skills/",
)

_RENDERED_ARTIFACT_FILES = frozenset({"CLAUDE.md", "AGENTS.md"})


def is_user_file(rel_path: str) -> bool:
    if rel_path in _RENDERED_ARTIFACT_FILES:
        return False
    return not any(
        rel_path == p.rstrip("/") or rel_path.startswith(p) for p in _FILE_HIDE_PREFIXES
    )


def resolve_workspace_path(
    name: str,
    *,
    settings: Settings,
) -> tuple[Path, Path]:
    return _ws().resolve_workspace_path(name, settings=settings)


def _safe_resolve(ws_path: Path, rel: str) -> Path:
    target = (ws_path / rel).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise WorkspacePathEscape(rel)
    return target


def read_file_by_name(
    name: str,
    path: str,
    *,
    settings: Settings,
) -> dict | None:
    return _ws().read_workspace_file(name, path, settings=settings)


def write_file_by_name(
    name: str,
    path: str,
    content: str,
    *,
    settings: Settings,
) -> dict:
    return _ws().write_workspace_file(name, path, content, settings=settings)


# ---------------------------------------------------------------------------
# Legacy agent-centric endpoints
# ---------------------------------------------------------------------------


def get_workspace_for_agent(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, agent_defs=agent_defs)
    info = ws.info(agent, settings, None)
    files: list[dict] = []
    if info.exists:
        for p in sorted(info.path.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(info.path))
                if not is_user_file(rel):
                    continue
                files.append({"path": rel, "size": p.stat().st_size})
    return {
        "agent_id": info.agent_id,
        "path": str(info.path),
        "exists": info.exists,
        "ephemeral": info.ephemeral,
        "files": files,
        "generated_configs": {},
    }


def create_workspace_for_agent(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, agent_defs=agent_defs)
    path = ws.ensure(agent, settings, None, scaffold=True)
    return {"path": str(path)}


def reset_workspace_for_agent(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, agent_defs=agent_defs)
    path = ws.reset(agent, settings, None)
    return {"path": str(path)}


def read_file_for_agent(
    agent_id: str,
    path: str,
    *,
    agent_defs: AgentDefManager,
    settings: Settings,
) -> dict | None:
    agent = _resolve_agent_or_raise(agent_id, agent_defs=agent_defs)
    ws_path, _ = ws.resolve_path(agent, settings, None)
    target = _safe_resolve(ws_path, path)
    if not target.is_file():
        return None
    return {"path": path, "content": target.read_text(encoding="utf-8")}


def write_file_for_agent(
    agent_id: str,
    path: str,
    content: str,
    *,
    agent_defs: AgentDefManager,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, agent_defs=agent_defs)
    ws_path = ws.ensure(agent, settings, None, scaffold=False)
    target = _safe_resolve(ws_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content)}
