"""Per-workspace runner config generation (Claude / OpenCode).

Delegates to ``WorkspaceService`` for config generation. The ``store``
parameter is retained for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.db import SessionStore
from agentbox.core.service.workspaces.service import WorkspaceService

from .files import _resolve_agent_or_raise

__all__ = [
    "generate_configs_by_name",
    "generate_configs_for_agent",
    "launch_runner_configs",
]


def _ws() -> WorkspaceService:
    return WorkspaceService()


def launch_runner_configs(
    workspace_path: Path,
    *,
    store: SessionStore,
    settings: Settings,
    servers: list[dict] | None = None,
    keep: bool = False,
):
    """Context manager — delegates to WorkspaceService."""
    return _ws().launch_runner_configs(
        workspace_path, servers=servers, keep=keep
    )


def generate_configs_by_name(
    name: str,
    *,
    store: SessionStore,
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    return _ws().generate_configs(name, settings=settings)


def generate_configs_for_agent(
    agent_id: str,
    *,
    store: SessionStore,
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, store=store)
    workspace_path, _ = ws.resolve_path(agent, settings, store)
    workspace_id = (
        agent.workspace
        if agent.workspace and agent.workspace != "<ephemeral>"
        else agent_id
    )
    paths = _ws().generate_configs(workspace_id, settings=settings)
    return {
        "workspace": str(workspace_path),
        "generated": paths.get("generated", {}),
    }
