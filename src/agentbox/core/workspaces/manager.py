"""Deprecated shims — kept for backward compatibility.

New code should import from ``agentbox.core.workspaces.crud`` directly.

The functions below will be removed in a future release.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

from agentbox.core.config import Settings
from agentbox.core.db import AgentDef, SessionStore
from agentbox.core.workspaces.crud import WorkspaceInfo, info, resolve_path

__all__ = [
    "WorkspaceInfo",
    "info",
    "list_all",
    "claude_agents_path",
    "claude_settings_path",
    "opencode_config_path",
    "reset",
    "resolve_path",
    "ensure",
]


def list_all(store: SessionStore, settings: Settings) -> list[WorkspaceInfo]:
    """Deprecated: moved to ``core.service.workspaces.registry.list_all_workspaces``."""
    warnings.warn(
        "manager.list_all is deprecated; use list_all_workspaces from "
        "core.service.workspaces.registry",
        DeprecationWarning,
        stacklevel=2,
    )
    agents = store.list_agents_with_latest()
    return [info(cast(AgentDef, a), settings, store) for a in agents]


# Re-export crud operations for backward compatibility
from agentbox.core.workspaces.crud import ensure, reset  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Deprecated generated config paths — kept for legacy runner compatibility.
# Generated configs are now written to per-run tmpfs dirs by the executor.
# ---------------------------------------------------------------------------


def _generated_dir(workspace_path: Path) -> Path:
    return workspace_path / ".agentbox" / "generated"


def claude_agents_path(workspace_path: Path) -> Path:
    """Deprecated: generated configs are now per-run."""
    return _generated_dir(workspace_path) / "claude_agents.json"


def claude_settings_path(workspace_path: Path) -> Path:
    """Deprecated: generated configs are now per-run."""
    return _generated_dir(workspace_path) / "claude_settings.json"


def opencode_config_path(workspace_path: Path) -> Path:
    """Deprecated: generated configs are now per-run."""
    return _generated_dir(workspace_path) / "opencode.json"
