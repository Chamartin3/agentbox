"""Deprecated shims — kept for backward compatibility.

New code should import from ``agentbox.core.workspaces.crud`` directly.

The functions below will be removed in a future release.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from agentbox.config import Settings
from agentbox.core.data import SessionStore
from agentbox.core.workspaces.crud import WorkspaceInfo, info, resolve_path

__all__ = [
    "WorkspaceInfo",
    "info",
    "list_all",
    "load_capabilities",
    "capabilities_path",
    "claude_agents_path",
    "claude_settings_path",
    "opencode_config_path",
    "reset",
    "resolve_path",
    "ensure",
]


def list_all(store: SessionStore, settings: Settings) -> list[WorkspaceInfo]:
    """Deprecated: moved to ``core.service.workspaces``."""
    from agentbox.core.service.agents import list_all_agents

    return [info(a, settings, store) for a in list_all_agents(store=store)]


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


# ---------------------------------------------------------------------------
# Workspace runtime config (permissions/capabilities.json)
# ---------------------------------------------------------------------------


def capabilities_path(workspace_path: Path) -> Path:
    """Deprecated: return path to the workspace's runtime capabilities config."""
    return workspace_path / "permissions" / "capabilities.json"


def load_capabilities(workspace_path: Path) -> dict:
    """Deprecated: read workspace capabilities.json, returning {} if missing/unparseable.

    This is a compatibility shim. Permissions are now inlined in the manifest
    via WorkspaceDef.allowed_tools, allowed_builtin_tools, etc.

    This function will be removed in a future release.

    Schema (all optional):
      - allowed_tools: list[str]
      - mcp_config_path: str | None  (project-relative)
      - max_tokens: int
      - allow_file_write: bool
      - allow_network: bool
    """
    path = capabilities_path(workspace_path)
    if path.is_file():
        warnings.warn(
            f"Found deprecated capabilities.json at {path}. "
            "Permissions are now inlined in agentbox.toml. "
            "Run `agentbox migrate workspace-permissions` to migrate. "
            "See docs/plans/05-workspace-inlining.md",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}
