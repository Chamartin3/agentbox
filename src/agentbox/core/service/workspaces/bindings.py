"""Service layer for workspace subagent and skill bindings."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from agentbox.core.service.resources.service import BindingError, ResourceService
from agentbox.core.service.workspaces.service import WorkspaceService

if TYPE_CHECKING:
    from agentbox.core.db import AgentDefManager

__all__ = [
    "list_workspace_subagents",
    "replace_workspace_subagents",
    "list_workspace_skill_bindings",
    "replace_workspace_skill_bindings",
]


# ---------------------------------------------------------------------------
# Subagents
# ---------------------------------------------------------------------------


def list_workspace_subagents(workspace_id: str, *, agent_defs: AgentDefManager) -> dict:
    svc = WorkspaceService()
    items = svc.list_workspace_subagents_raw(workspace_id)
    enriched = []
    for s in items:
        agent = agent_defs.get(s["agent_id"])
        enriched.append(
            {
                **s,
                "agent_name": getattr(agent, "name", None) if agent else None,
                "agent_description": getattr(agent, "description", None)
                if agent
                else None,
            }
        )
    return {"items": enriched}


def replace_workspace_subagents(
    workspace_id: str,
    subagents: list[dict],
    *,
    actor: str | None = None,
    settings: Any = None,
    sync_cb: Any = None,
) -> dict:
    svc = WorkspaceService()
    try:
        items = svc.replace_workspace_subagents(workspace_id, subagents, actor=actor)
    except ValueError as exc:
        raise BindingError(str(exc)) from exc
    if sync_cb is not None and settings is not None:
        with contextlib.suppress(Exception):
            sync_cb(settings, workspace_id)
    return {"items": items}


# ---------------------------------------------------------------------------
# Skill bindings
# ---------------------------------------------------------------------------


def list_workspace_skill_bindings(workspace_id: str) -> dict:
    return ResourceService().list_workspace_skill_bindings(workspace_id)


def replace_workspace_skill_bindings(
    workspace_id: str,
    skill_resource_ids: list[str],
    *,
    reason: str,
    actor: str | None = None,
    settings: Any = None,
    sync_cb: Any = None,
) -> dict:
    svc = ResourceService()
    try:
        result = svc.replace_workspace_skill_bindings(
            workspace_id, skill_resource_ids, reason=reason, actor=actor
        )
    except ValueError as exc:
        raise BindingError(str(exc)) from exc
    if sync_cb is not None and settings is not None:
        with contextlib.suppress(Exception):
            sync_cb(settings, workspace_id)
    return result
