"""workspaces permissions — get/set workspace permissions."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from agentbox.cli._deps import get_settings, get_store
from agentbox.cli._common import console
from agentbox.core.service import workspaces as workspaces_service
from agentbox.core.service.workspaces.errors import WorkspaceNotFound

permissions_app = typer.Typer(
    name="permissions",
    help="Get or set workspace permissions.",
    no_args_is_help=True,
)


@permissions_app.command("get")
def permissions_get(
    name: str = typer.Argument(..., help="Workspace name"),
) -> None:
    """Show current permissions for a workspace."""
    store = get_store()
    try:
        result = workspaces_service.get_permissions(
            name, store=store, settings=get_settings()
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)

    console.print(
        Panel(
            Syntax(
                json.dumps(result, indent=2, default=str),
                "json",
                theme="ansi_dark",
            ),
            title=f"Permissions — {name}",
        )
    )


@permissions_app.command("put")
def permissions_put(
    name: str = typer.Argument(..., help="Workspace name"),
    permissions_json: str = typer.Argument(
        ..., help="JSON permissions payload"
    ),
) -> None:
    """Set permissions for a workspace.

    Example:
        workspaces permissions put my-ws '{"allow": ["read"], "deny": []}'
    """
    try:
        permissions = json.loads(permissions_json)
    except json.JSONDecodeError as exc:
        console.print(f"[red]invalid JSON: {exc}[/red]")
        raise typer.Exit(2)

    store = get_store()
    try:
        workspaces_service.set_permissions(
            name, permissions, store=store, settings=get_settings()
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[green]permissions updated[/green] for {name!r}")
