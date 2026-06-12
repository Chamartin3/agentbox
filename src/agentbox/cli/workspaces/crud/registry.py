"""Registry CRUD commands: create, delete named workspaces."""

from __future__ import annotations

import typer

from agentbox.cli._common import console
from agentbox.cli._deps import get_settings, get_store
from agentbox.core.service import workspaces as workspaces_service
from agentbox.core.service.workspaces.errors import (
    WorkspaceExists,
    WorkspaceNotFound,
)
from agentbox.cli.workspaces.crud._app import ws_app


@ws_app.command("create")
def ws_create(
    name: str = typer.Argument(..., help="Workspace name"),
    description: str | None = typer.Option(
        None, "--description", help="Optional description"
    ),
    path: str | None = typer.Option(
        None, "--path", help="Optional workspace path relative to project root"
    ),
) -> None:
    """Create a named workspace in the DB registry."""
    store = get_store()
    try:
        result = workspaces_service.create_workspace_registry(
            name,
            store=store,
            description=description,
            path=path,
        )
    except WorkspaceExists as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]created[/green] workspace {result['name']!r}")


@ws_app.command("delete")
def ws_delete(
    name: str = typer.Argument(..., help="Workspace name"),
    purge_disk: bool = typer.Option(
        False, "--purge-disk", help="Also delete the workspace directory on disk"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a named workspace from the DB registry."""
    if not yes:
        confirm = typer.confirm(f"Delete workspace {name!r}?")
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
