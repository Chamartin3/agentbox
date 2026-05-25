"""Per-workspace runner config generation (Claude / OpenCode)."""

from __future__ import annotations

from typing import Any

from agentbox.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.data import SessionStore

from ._files import _resolve_agent_or_raise, resolve_workspace_path
from ._permissions import _make_generator, load_effective_permissions

__all__ = ["generate_configs_by_name", "generate_configs_for_agent"]


def generate_configs_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any = None,
    mcp_manifest: Any | None = None,
) -> dict:
    ws_path, project_root = resolve_workspace_path(
        name, store=store, settings=settings, loader=loader
    )
    permissions = load_effective_permissions(
        name,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    allowed_tools = set(permissions.get("allowed_tools", []))
    allowed_builtin_tools = permissions.get("allowed_builtin_tools") or []
    files = permissions.get("files") or []

    generator = _make_generator(project_root, store, mcp_manifest)
    paths = generator.generate_for_workspace(
        ws_path,
        allowed_tools=allowed_tools if allowed_tools else None,
        allowed_builtin_tools=allowed_builtin_tools,
        files=files,
        project_root=project_root,
    )
    return {
        "workspace": str(ws_path),
        "generated": {k: str(v) for k, v in paths.items()},
    }


def generate_configs_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    loader: Any,
    mcp_manifest: Any | None = None,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, loader=loader)
    workspace_path, _ = ws.resolve_path(agent, settings, store)
    permissions = load_effective_permissions(
        agent.workspace,
        store=store,
        settings=settings,
        loader=loader,
        mcp_manifest=mcp_manifest,
    )
    generator = _make_generator(settings.project_root, store, mcp_manifest)
    paths = generator.generate_for_workspace(
        workspace_path,
        allowed_builtin_tools=permissions.get("allowed_builtin_tools") or [],
        files=permissions.get("files") or [],
        project_root=settings.project_root,
    )
    return {
        "workspace": str(workspace_path),
        "generated": {k: str(v) for k, v in paths.items()},
    }
