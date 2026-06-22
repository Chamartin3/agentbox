"""Work workspaces — ls, new, edit, rm, shell, explore."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer
from rich.table import Table
from rich.text import Text

from agentbox.cli.shared import checkmark, console, resolve_agent, get_settings, get_store
from agentbox.cli.ops.launch import _launch_session
from agentbox.core import workspaces as ws_core
from agentbox.core.service import workspaces as workspaces_service
from agentbox.core.service.workspaces.errors import WorkspaceNotFound
from agentbox.core.service import get_workspace as service_get_workspace


def _resolve_workspace(name: str) -> tuple[Path, str]:
    """Resolve a workspace path from name or agent ID."""
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
    ws_path = ws_core.ensure(a, settings, store, scaffold=True)
    return ws_path, name


def _delegate_shell(name: str | None, generate: bool) -> int:
    """Resolve name and delegate to launch."""
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

ws_app = typer.Typer(
    name="ws",
    help="Manage workspaces: ls, new, edit, rm, shell, explore.",
    no_args_is_help=True,
)


@ws_app.command("ls")
def ws_ls() -> None:
    """List all configured agents and their workspaces."""
    settings = get_settings()
    rows = ws_core.list_all(get_store(), settings)
    if not rows:
        console.print("[yellow]No agents declared.[/yellow]")
        return

    table = Table(
        title="Workspaces", title_style="bold", header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("State", justify="center", width=7)
    table.add_column("Agent", style="bold")
    table.add_column("Path", style="dim")
    table.add_column("CLAUDE.md", justify="center")
    table.add_column("Skills", justify="right", style="magenta")

    for w in rows:
        if w.ephemeral:
            state = Text("EPH", style="bold yellow")
        elif w.exists:
            state = Text("OK", style="bold green")
        else:
            state = Text("NEW", style="bold blue")
        table.add_row(
            state, w.agent_id, str(w.path),
            checkmark(w.has_claude_md),
            str(w.skill_count) if w.skill_count else "[dim]\u00b7[/dim]",
        )
    console.print(table)
    console.print(
        "[dim]Legend:[/dim] "
        "[bold green]OK[/bold green]=exists  "
        "[bold blue]NEW[/bold blue]=not created yet  "
        "[bold yellow]EPH[/bold yellow]=ephemeral (tmp per run)"
    )


@ws_app.command("show")
def ws_show(
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
) -> None:
    """Print the absolute path of a workspace."""
    target = name or "default"
    path, _ = _resolve_workspace(target)
    typer.echo(str(path))


@ws_app.command("new")
def ws_new(
    agent: str,
    scaffold: bool = True,
    reset: bool = typer.Option(False, "--reset", help="Delete and recreate"),
    register: bool = typer.Option(
        False, "--register", help="Register as a named workspace"
    ),
) -> None:
    """Create or recreate the workspace directory."""
    if reset:
        a = resolve_agent(agent)
        path = ws_core.reset(a, get_settings(), get_store())
        console.print(f"[yellow]\u21bb[/yellow] reset: [bold]{path}[/bold]")
        return

    a = resolve_agent(agent)
    path = ws_core.ensure(a, get_settings(), get_store(), scaffold=scaffold)
    console.print(f"[green]\u2713[/green] workspace ready: [bold]{path}[/bold]")


@ws_app.command("edit")
def ws_edit(
    agent: str,
    file: str = typer.Option("CLAUDE.md", help="File within workspace to open"),
) -> None:
    """Open a workspace file in $EDITOR (falls back to vi)."""
    a = resolve_agent(agent)
    path = ws_core.ensure(a, get_settings(), get_store(), scaffold=True)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.call([editor, str(path / file)])


@ws_app.command("rm")
def ws_rm(
    name: str = typer.Argument(..., help="Workspace name to delete"),
    purge_disk: bool = typer.Option(
        False, "--purge-disk", help="Also delete the workspace directory on disk"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a named workspace from the DB registry."""
    if not yes:
        confirm = typer.confirm(
            f"Delete workspace {name!r}? This cannot be undone."
        )
        if not confirm:
            raise typer.Exit(0)
    store = get_store()
    try:
        result = workspaces_service.delete_workspace_registry(
            name,
            store=store,
            settings=get_settings(),
            purge_disk=purge_disk,
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[yellow]deleted[/yellow] workspace {result['name']!r}")


@ws_app.command("shell")
def ws_shell(
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
    generate: bool = typer.Option(
        False, "--generate", help="Keep generated config files"
    ),
) -> None:
    """Open an interactive shell in a fully-built workspace."""
    _delegate_shell(name, generate=generate)


@ws_app.command("explore")
def ws_explore(
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
) -> None:
    """Open a shell in a workspace with a yazi tip."""
    path, _ = _resolve_workspace(name or "default")
    typer.echo(f"  [bold cyan]yazi[/bold cyan] [dim]{path}[/dim]")
