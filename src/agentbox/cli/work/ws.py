"""Work workspaces — ls, new, edit, rm, shell, explore."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext, resolve_agent
# TODO(cli-arch): launch orchestration → Service (plans 089/101)
from agentbox.cli.ops.launch import _launch_session
# TODO(cli-arch): workspace CRUD → WorkspaceService (plan 089)
from agentbox.core import service as ws_core
# TODO(cli-arch): move to facade export
from agentbox.core.data.errors import WorkspaceNotFound


def _resolve_workspace(obj: CLIContext, name: str) -> tuple[Path, str]:
    """Resolve a workspace path from name or agent ID."""
    row = obj.workspaces.get_workspace(name)
    if row:
        rel = row.get("path")
        if rel:
            path = obj.settings.project_root / rel
            path.mkdir(parents=True, exist_ok=True)
            return path, name
    a = resolve_agent(name)
    ws_path = ws_core.ensure(a, obj.settings)
    return ws_path, name


def _delegate_shell(obj: CLIContext, name: str | None, *, generate: bool) -> int:
    """Resolve name and delegate to launch."""
    workspace_arg: str | None = None
    agent_arg: str | None = None
    if name and name != "default":
        row = obj.workspaces.get_workspace(name)
        if row:
            workspace_arg = name
        else:
            agent_arg = name
    return _launch_session(
        obj=obj,
        runner="shell",
        agent=agent_arg,
        workspace=workspace_arg,
        model=None,
        ephemeral=False,
        keep_configs=generate,
    )


ws_app = typer.Typer(
    name="ws",
    help="Manage workspaces: ls, new, edit, rm, shell, explore.",
    no_args_is_help=True,
)


@ws_app.command("ls")
def ws_ls(ctx: typer.Context) -> None:
    """List all configured agents and their workspaces."""
    obj: CLIContext = ctx.obj
    rows = [
        ws_core.info(a, obj.settings)
        for a in obj.agents.list_all_agents()
    ]
    obj.render.workspace.workspaces_table(rows)


@ws_app.command("show")
def ws_show(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
) -> None:
    """Print the absolute path of a workspace."""
    obj: CLIContext = ctx.obj
    target = name or "default"
    path, _ = _resolve_workspace(obj, target)
    obj.render.workspace.workspace_path(path)


@ws_app.command("new")
def ws_new(
    ctx: typer.Context,
    agent: str,
    reset: bool = typer.Option(False, "--reset", help="Delete and recreate"),
    register: bool = typer.Option(
        False, "--register", help="Register as a named workspace"
    ),
) -> None:
    """Create or recreate the workspace directory."""
    obj: CLIContext = ctx.obj
    if reset:
        a = resolve_agent(agent)
        path = ws_core.reset(a, obj.settings)
        obj.render.workspace.workspace_reset(path)
        return

    a = resolve_agent(agent)
    path = ws_core.ensure(a, obj.settings)
    obj.render.workspace.workspace_ready(path)


@ws_app.command("edit")
def ws_edit(
    ctx: typer.Context,
    agent: str,
    file: str = typer.Option("CLAUDE.md", help="File within workspace to open"),
) -> None:
    """Open a workspace file in $EDITOR (falls back to vi)."""
    obj: CLIContext = ctx.obj
    a = resolve_agent(agent)
    path = ws_core.ensure(a, obj.settings)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.call([editor, str(path / file)])


@ws_app.command("rm")
def ws_rm(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name to delete"),
    purge_disk: bool = typer.Option(
        False, "--purge-disk", help="Also delete the workspace directory on disk"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a named workspace from the DB registry."""
    obj: CLIContext = ctx.obj
    if not yes:
        confirm = typer.confirm(
            f"Delete workspace {name!r}? This cannot be undone."
        )
        if not confirm:
            raise typer.Exit(0)
    try:
        result = obj.workspaces.delete_workspace(
            name,
            settings=obj.settings,
            purge_disk=purge_disk,
        )
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)
    obj.render.workspace.workspace_deleted(str(result["deleted"]))


@ws_app.command("shell")
def ws_shell(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
    generate: bool = typer.Option(
        False, "--generate", help="Keep generated config files"
    ),
) -> None:
    """Open an interactive shell in a fully-built workspace."""
    obj: CLIContext = ctx.obj
    _delegate_shell(obj, name, generate=generate)


@ws_app.command("explore")
def ws_explore(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
) -> None:
    """Open a shell in a workspace with a yazi tip."""
    obj: CLIContext = ctx.obj
    path, _ = _resolve_workspace(obj, name or "default")
    obj.render.workspace.dim(f"  [bold cyan]yazi[/bold cyan] [dim]{path}[/dim]")
