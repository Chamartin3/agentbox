from __future__ import annotations

import os
import subprocess

import typer
from rich.text import Text

from agentbox.api.deps import get_loader, get_settings
from agentbox.cli._common import checkmark, console, resolve_agent
from agentbox.core import workspaces as ws

ws_app = typer.Typer(
    name="ws",
    help="Manage per-agent workspaces.",
    no_args_is_help=True,
)


@ws_app.command("ls")
def ws_ls() -> None:
    """List all configured agents and their workspaces."""
    from rich.table import Table

    loader = get_loader()
    settings = get_settings()
    rows = ws.list_all(loader, settings)
    if not rows:
        console.print("[yellow]No agents declared.[/yellow]")
        return

    table = Table(
        title="Workspaces",
        title_style="bold",
        header_style="bold cyan",
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
            state,
            w.agent_id,
            str(w.path),
            checkmark(w.has_claude_md),
            str(w.skill_count) if w.skill_count else "[dim]·[/dim]",
        )
    console.print(table)
    console.print(
        "[dim]Legend:[/dim] "
        "[bold green]OK[/bold green]=exists  "
        "[bold blue]NEW[/bold blue]=not created yet  "
        "[bold yellow]EPH[/bold yellow]=ephemeral (tmp per run)"
    )


@ws_app.command("path")
def ws_path(agent: str) -> None:
    """Print the absolute path of an agent's workspace."""
    a = resolve_agent(agent)
    path, _eph = ws.resolve_path(a, get_settings(), get_loader())
    typer.echo(str(path))


@ws_app.command("new")
def ws_new(agent: str, scaffold: bool = True) -> None:
    """Create the workspace directory (and scaffold a starter CLAUDE.md)."""
    a = resolve_agent(agent)
    path = ws.ensure(a, get_settings(), get_loader(), scaffold=scaffold)
    console.print(f"[green]✓[/green] workspace ready: [bold]{path}[/bold]")


@ws_app.command("reset")
def ws_reset(
    agent: str,
    confirm: bool = typer.Option(False, "--yes", help="Confirm destructive op"),
) -> None:
    """Delete and recreate the workspace (drops everything inside)."""
    if not confirm:
        console.print(
            "[red]refusing without --yes[/red] (this deletes the workspace contents)"
        )
        raise typer.Exit(2)
    a = resolve_agent(agent)
    path = ws.reset(a, get_settings(), get_loader())
    console.print(f"[yellow]↻[/yellow] reset: [bold]{path}[/bold]")


@ws_app.command("edit")
def ws_edit(
    agent: str,
    file: str = typer.Option("CLAUDE.md", help="File within workspace to open"),
) -> None:
    """Open a workspace file in $EDITOR (falls back to vi)."""
    a = resolve_agent(agent)
    path = ws.ensure(a, get_settings(), get_loader(), scaffold=True)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.call([editor, str(path / file)])
