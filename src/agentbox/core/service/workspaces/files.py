"""Workspace file IO, path resolution, and the ``is_user_file`` filter.

This module owns the low-level path helpers (``resolve_workspace_path``,
``_safe_resolve``) because every other submodule needs them and keeping
them here avoids circular imports across the package.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.db import SessionStore
from agentbox.core.service.prompts import AgentNotFound

from .errors import WorkspaceNotFound, WorkspacePathEscape

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


def _resolve_agent_or_raise(agent_id: str, *, store: SessionStore):
    agent = store.get_agent_def(agent_id)
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
    """User files are anything outside generated/permissions/skill dirs and
    not a render artifact at the workspace root.
    """
    if rel_path in _RENDERED_ARTIFACT_FILES:
        return False
    return not any(
        rel_path == p.rstrip("/") or rel_path.startswith(p) for p in _FILE_HIDE_PREFIXES
    )


def resolve_workspace_path(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> tuple[Path, Path]:
    """Return ``(workspace_path, project_root)`` for a named workspace.

    Registry-first: the canonical ``workspaces`` table is the source of
    truth for existence. Raises :class:`WorkspaceNotFound` when the name
    is unknown.
    """
    row = store.get_workspace(name)
    if row is None:
        raise WorkspaceNotFound(name)
    rel_path = row.get("path")
    ws_path = (
        settings.project_root / rel_path
        if rel_path
        else settings.workspaces_root / name
    )
    return ws_path, settings.project_root


def _safe_resolve(ws_path: Path, rel: str) -> Path:
    target = (ws_path / rel).resolve()
    if not str(target).startswith(str(ws_path.resolve())):
        raise WorkspacePathEscape(rel)
    return target


def read_file_by_name(
    name: str,
    path: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict | None:
    ws_path, _ = resolve_workspace_path(name, store=store, settings=settings)
    target = _safe_resolve(ws_path, path)
    if not target.is_file():
        return None
    return {"path": path, "content": target.read_text(encoding="utf-8")}


def write_file_by_name(
    name: str,
    path: str,
    content: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict:
    ws_path, _ = resolve_workspace_path(name, store=store, settings=settings)
    target = _safe_resolve(ws_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content)}


# ---------------------------------------------------------------------------
# Legacy agent-centric endpoints
# ---------------------------------------------------------------------------


def get_workspace_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    info = ws.info(agent, settings, store)
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
    store: SessionStore,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    path = ws.ensure(agent, settings, store, scaffold=True)
    return {"path": str(path)}


def reset_workspace_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    path = ws.reset(agent, settings, store)
    return {"path": str(path)}


def read_file_for_agent(
    agent_id: str,
    path: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict | None:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    ws_path, _ = ws.resolve_path(agent, settings, store)
    target = _safe_resolve(ws_path, path)
    if not target.is_file():
        return None
    return {"path": path, "content": target.read_text(encoding="utf-8")}


def write_file_for_agent(
    agent_id: str,
    path: str,
    content: str,
    *,
    store: SessionStore,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    ws_path = ws.ensure(agent, settings, store, scaffold=False)
    target = _safe_resolve(ws_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "bytes": len(content)}
