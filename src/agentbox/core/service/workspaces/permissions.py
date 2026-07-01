"""Runtime workspace permissions overlay.

Delegates to ``WorkspaceService`` for core permission operations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.service.workspaces.service import WorkspaceService


__all__ = [
    "get_permissions",
    "set_permissions",
    "get_workspace_mcp_tools",
    "load_effective_permissions",
]


def _ws() -> WorkspaceService:
    return WorkspaceService()


def _is_read_tool(tool: str) -> bool:
    _READ_PREFIXES: frozenset[str] = frozenset(
        {"list_", "get_", "search_", "check_", "select_", "find_"}
    )
    return any(tool.startswith(rp) for rp in _READ_PREFIXES)


def load_effective_permissions(
    name: str | None,
    *,
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    return _ws().load_effective_permissions(name or "")


def _write_capabilities_artifact(ws_path: Path, permissions: dict) -> None:
    perm_dir = ws_path / "permissions"
    perm_dir.mkdir(parents=True, exist_ok=True)
    perm_file = perm_dir / "capabilities.json"
    perm_file.write_text(
        json.dumps(permissions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_permissions(
    name: str,
    *,
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    return _ws().get_permissions(name)


def set_permissions(
    name: str,
    permissions: dict,
    *,
    settings: Settings,
    mcp_manifest: Any | None = None,
    sync_cb: Any = None,
) -> dict:
    svc = _ws()
    return svc.set_permissions(name, permissions, settings=settings, sync_cb=sync_cb)


def get_workspace_mcp_tools(
    name: str,
    *,
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    return _ws().get_workspace_mcp_tools(name)
