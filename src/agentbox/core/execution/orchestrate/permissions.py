"""Workspace permissions resolution extracted from RunSetup."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.config import Settings
from agentbox.core.data import AgentDef

if TYPE_CHECKING:
    from agentbox.core.data import RunSetupStore


def load_workspace_permissions(
    workdir: Path,
    agent: AgentDef,
    settings: Settings,
    store: RunSetupStore | None = None,
) -> dict:
    """Resolve effective workspace permissions from the DB overlay.

    ``workspace_runtime_permissions`` is the single source of truth for
    built-in tools, file scopes, max_tokens, and network/write flags.
    Workspaces with no overlay row receive an empty permissions dict —
    callers downstream treat that as "no constraints declared".
    """
    if not agent.workspace or agent.workspace == "<ephemeral>":
        return {}
    if store is None:
        return {}
    try:
        overlay = store.get_workspace_runtime_permissions(agent.workspace)
    except Exception:
        return {}
    if not overlay:
        return {}
    perms: dict = {}
    if overlay.get("allowed_builtin_tools") is not None:
        perms["allowed_builtin_tools"] = overlay["allowed_builtin_tools"]
    if overlay.get("files") is not None:
        perms["files"] = overlay["files"]
    if overlay.get("max_tokens") is not None:
        perms["max_tokens"] = overlay["max_tokens"]
    if overlay.get("allow_file_write") is not None:
        perms["allow_file_write"] = bool(overlay["allow_file_write"])
    if overlay.get("allow_network") is not None:
        perms["allow_network"] = bool(overlay["allow_network"])
    return perms
