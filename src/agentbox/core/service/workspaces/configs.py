"""Per-workspace runner config generation (Claude / OpenCode).

Delegates to ``WorkspaceService`` for config generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.service.agents.service import AgentService
from agentbox.core.service.workspaces.service import WorkspaceService

from agentbox.core.service.agents.versions import AgentNotFound

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
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    return _ws().generate_configs(name, settings=settings)


def generate_configs_for_agent(
    agent_id: str,
    *,
    settings: Settings,
    mcp_manifest: Any | None = None,
) -> dict:
    agent = AgentService().get_agent_def(agent_id)
    if agent is None:
        raise AgentNotFound(agent_id)
    workspace_path, _ = ws.resolve_path(agent, settings)
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
