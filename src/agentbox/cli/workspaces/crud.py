from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer
from rich.text import Text

from agentbox.api.deps import get_settings, get_store
from agentbox.cli._common import checkmark, console, resolve_agent
from agentbox.core import workspaces as ws

ws_app = typer.Typer(
    name="ws",
    help="Manage per-agent workspaces. Default: open a shell in the default workspace.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@ws_app.callback()
def ws_default(ctx: typer.Context) -> None:
    """Default: open a shell in the default workspace."""
    if ctx.invoked_subcommand is None:
        ws_shell(name=None)


@ws_app.command("ls")
def ws_ls() -> None:
    """List all configured agents and their workspaces."""
    from rich.table import Table

    settings = get_settings()
    rows = ws.list_all(get_store(), settings)
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
def ws_path(
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
) -> None:
    """Print the absolute path of a workspace or an agent's workspace."""
    target = name or "default"
    path, _ = _resolve_workspace(target)
    typer.echo(str(path))


@ws_app.command("new")
def ws_new(agent: str, scaffold: bool = True) -> None:
    """Create the workspace directory (and scaffold a starter CLAUDE.md)."""
    a = resolve_agent(agent)
    path = ws.ensure(a, get_settings(), get_store(), scaffold=scaffold)
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
    path = ws.reset(a, get_settings(), get_store())
    console.print(f"[yellow]↻[/yellow] reset: [bold]{path}[/bold]")


@ws_app.command("edit")
def ws_edit(
    agent: str,
    file: str = typer.Option("CLAUDE.md", help="File within workspace to open"),
) -> None:
    """Open a workspace file in $EDITOR (falls back to vi)."""
    a = resolve_agent(agent)
    path = ws.ensure(a, get_settings(), get_store(), scaffold=True)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.call([editor, str(path / file)])


# ---------------------------------------------------------------------------
# shell / explore
# ---------------------------------------------------------------------------


def _resolve_workspace(
    name: str,
) -> tuple[Path, str]:
    """Resolve a workspace path from a named workspace or agent ID.

    Tries named workspace first, then falls back to agent lookup.
    Returns (path, label) where label is the display name.
    """
    settings = get_settings()
    store = get_store()

    row = store.get_workspace(name) if hasattr(store, "get_workspace") else None
    if row and row.get("path"):
        path = settings.project_root / row["path"]
        path.mkdir(parents=True, exist_ok=True)
        return path, name

    a = resolve_agent(name)
    path = ws.ensure(a, settings, store, scaffold=True)
    return path, name


def _delegate_shell(name: str | None, generate: bool) -> int:
    """Resolve ``name`` to a workspace or agent ID and delegate to ``launch``.

    Preserves the legacy ``ws shell <name>`` semantics: try a named
    workspace first; if that doesn't match, treat ``name`` as an agent ID
    and let the launch resolver use the agent's declared workspace.
    """
    from agentbox.cli.launch import _launch_session

    store = get_store()
    workspace_arg: str | None = None
    agent_arg: str | None = None
    if name and name != "default":
        row = store.get_workspace(name) if hasattr(store, "get_workspace") else None
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


@ws_app.command("shell")
def ws_shell(
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
    generate: bool = typer.Option(
        True,
        "--generate/--no-generate",
        help="Generate runner configs into workspace/.agentbox/generated",
    ),
) -> None:
    """Open an interactive shell in a fully-built workspace.

    Thin wrapper around ``agentbox launch shell`` that accepts either a
    named workspace or an agent ID as the positional argument. Defaults
    to the ``default`` workspace.
    """
    raise SystemExit(_delegate_shell(name, generate))


@ws_app.command("explore")
def ws_explore(
    name: str | None = typer.Argument(None, help="Workspace name or agent ID"),
    generate: bool = typer.Option(
        True,
        "--generate/--no-generate",
        help="Generate runner configs into workspace/.agentbox/generated",
    ),
) -> None:
    """Open a shell in a workspace with a yazi tip.

    Same as ``ws shell`` — kept for backward compatibility.
    """
    console.print("[dim]Tip: run [bold]yazi[/bold] to browse the file tree[/dim]")
    raise SystemExit(_delegate_shell(name, generate))
