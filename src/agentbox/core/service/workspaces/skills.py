"""Workspace skill discovery, materialization, and content access.

Delegates to ``WorkspaceService``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.config import Settings
from agentbox.core import workspaces as ws
from agentbox.core.service.workspaces.service import WorkspaceService

from .files import _resolve_agent_or_raise

if TYPE_CHECKING:
    from agentbox.core.db import AgentDefManager

__all__ = [
    "generate_skills_by_name",
    "list_skills_by_name",
    "get_skill_content_by_name",
    "list_skills_for_agent",
]


def _ws() -> WorkspaceService:
    return WorkspaceService()


def generate_skills_by_name(
    name: str,
    *,
    settings: Settings,
) -> dict:
    return _ws().generate_skills(name, settings=settings)


def list_skills_by_name(
    name: str,
    *,
    settings: Settings,
) -> dict:
    return _ws().list_skills(name, settings=settings)


def get_skill_content_by_name(
    name: str,
    skill_name: str,
    *,
    settings: Settings,
) -> dict | None:
    return _ws().get_skill_content(name, skill_name, settings=settings)


def list_skills_for_agent(
    agent_id: str,
    *,
    agent_defs: AgentDefManager,
    settings: Settings,
) -> dict:
    agent = _resolve_agent_or_raise(agent_id, agent_defs=agent_defs)
    workspace_path, _ = ws.resolve_path(agent, settings, None)
    workspace_name = (
        agent.workspace
        if agent.workspace and agent.workspace != "<ephemeral>"
        else agent_id
    )
    skills_result = _ws().list_skills(workspace_name, settings=settings)
    return {
        "agent_id": agent_id,
        "workspace": str(workspace_path),
        "skills": skills_result.get("skills", []),
    }
