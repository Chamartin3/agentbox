"""Shared Typer app + helper utilities for ws commands."""

from __future__ import annotations

from pathlib import Path

import typer

from agentbox.cli._common import console, resolve_agent
from agentbox.cli._deps import get_settings, get_store
from agentbox.cli.ops.launch import _launch_session
from agentbox.core.service import get_workspace as service_get_workspace
from agentbox.core import workspaces as ws

ws_app = typer.Typer(
    name="ws",
    help="Manage per-agent workspaces. Default: open a shell in the default workspace.",
    no_args_is_help=False,
    invoke_without_command=True,
)


def _resolve_workspace(
    name: str,
) -> tuple[Path, str]:
    """Resolve a workspace path from a named workspace or agent ID.

    Tries named workspace first, then falls back to agent lookup.
    Returns (path, label) where label is the display name.
    """
    settings = get_settings()
    store = get_store()

    row = service_get_workspace(store, name) if hasattr(store, "get_workspace") else None
    if row:
        rel = row.get("path")
        if rel:
            path = settings.project_root / rel
            path.mkdir(parents=True, exist_ok=True)
            return path, name

    a = resolve_agent(name)
    ws_path = ws.ensure(a, settings, store, scaffold=True)
    return ws_path, name


def _delegate_shell(name: str | None, generate: bool) -> int:
    """Resolve ``name`` to a workspace or agent ID and delegate to ``launch``.

    Preserves the legacy ``ws shell <name>`` semantics: try a named
    workspace first; if that doesn't match, treat ``name`` as an agent ID
    and let the launch resolver use the agent's declared workspace.
    """
    store = get_store()
    workspace_arg: str | None = None
    agent_arg: str | None = None
    if name and name != "default":
        row = service_get_workspace(store, name) if hasattr(store, "get_workspace") else None
        if row:
            workspace_arg = name
        else:
            agent_arg = name

    return _launch_session(
        runner="shell",
        agent=agent_arg,
        workspace=workspace_arg,
        model=None,
        ephemeral=False,
        keep_configs=generate,
    )


__all__ = ["ws_app", "_resolve_workspace", "_delegate_shell", "console"]
