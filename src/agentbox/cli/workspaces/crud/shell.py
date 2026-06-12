"""Shell and explore workspace commands."""

from __future__ import annotations

import typer

from agentbox.cli._common import console
from agentbox.cli.workspaces.crud._app import ws_app, _delegate_shell


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
