"""Service layer for prompt + workspace resource bindings.

.. deprecated::
    These standalone functions are retained for backward compatibility
    with existing test code. New code should use ``ResourceService``
    directly from ``agentbox.core.service.resources.service``.
"""

from __future__ import annotations

import contextlib
from typing import Any

from agentbox.core.agents.composition.preview import PreviewError, render_agent_prompt_preview
from agentbox.core.constants import PromptMode, PromptSlot
from agentbox.core.db import SessionStore
from agentbox.core.service.resources.service import (
    AgentVersionMissing,
    BindingError,
    ResourceService,
)

__all__ = [
    "BindingError",
    "AgentVersionMissing",
    "PreviewError",
    "PromptMode",
    "PromptSlot",
    "list_prompt_resources",
    "replace_prompt_resources",
    "preview_prompt",
    "list_workspace_resources",
    "replace_workspace_resources",
    "dry_run_workspace_resources",
    "preview_modes",
]


def _svc() -> ResourceService:
    return ResourceService()


def list_prompt_resources(agent_id: str, *, store: SessionStore) -> dict:  # noqa: ARG001
    return _svc().list_prompt_resources(agent_id)


def replace_prompt_resources(agent_id: str, bindings: list[dict], *, store: SessionStore, reason: str, actor: str | None = None) -> dict:  # noqa: ARG001
    return _svc().replace_prompt_resources(agent_id, bindings, reason=reason, actor=actor)


def preview_prompt(agent_id: str, *, store: SessionStore, template: str | None = None, bindings_override: list[dict] | None = None) -> dict:  # noqa: ARG001
    if template is None:
        # Need to get the agent's prompt content. Use AgentService.
        from agentbox.core.service import AgentService  # noqa: PLC0415
        agent_svc = AgentService()
        agent = agent_svc.resolve_agent(agent_id)
        if agent is None:
            raise AgentVersionMissing(agent_id)
        template = agent.prompt or ""
    return render_agent_prompt_preview(store, agent_id=agent_id, template=template, bindings_override=bindings_override)


def list_workspace_resources(workspace_id: str, *, store: SessionStore) -> dict:  # noqa: ARG001
    return _svc().list_workspace_resources(workspace_id)


def replace_workspace_resources(workspace_id: str, bindings: list[dict], *, store: SessionStore, reason: str, actor: str | None = None, settings: Any = None, sync_cb: Any = None) -> dict:  # noqa: ARG001
    try:
        items = _svc().replace_workspace_resources(workspace_id, bindings, reason=reason, actor=actor)["items"]
    except ValueError as exc:
        raise BindingError(str(exc)) from exc
    if sync_cb is not None and settings is not None:
        with contextlib.suppress(Exception):
            sync_cb(store, settings, workspace_id)
    return {"items": items}


def dry_run_workspace_resources(workspace_id: str, *, store: SessionStore) -> dict:  # noqa: ARG001
    return _svc().dry_run_workspace_resources(workspace_id)


def preview_modes(resource_id: str, *, store: SessionStore) -> dict:  # noqa: ARG001
    return _svc().preview_modes(resource_id)
