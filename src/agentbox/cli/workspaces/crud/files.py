"""File and config-generation workspace commands."""

from __future__ import annotations

import sys

import typer

from agentbox.cli._common import console
from agentbox.cli._deps import get_settings, get_store
from agentbox.core.service import workspaces as workspaces_service
from agentbox.core.service.workspaces.errors import WorkspaceNotFound
from agentbox.cli.workspaces.crud._app import ws_app


@ws_app.command("generate-configs")
def ws_generate_configs(
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
) -> None:
    """Generate runner configs into a workspace."""
    try:
        result = workspaces_service.generate_configs_by_name(
            name,
            store=get_store(),
            settings=get_settings(),
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]configs generated[/green] → {result.get('target_dir', '?')} "
        f"({result.get('files_written', 0)} files)"
    )


@ws_app.command("generate-skills")
def ws_generate_skills(
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
) -> None:
    """Generate skill shell scripts into a workspace."""
    try:
        result = workspaces_service.generate_skills_by_name(
            name,
            store=get_store(),
            settings=get_settings(),
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]skills generated[/green] → {result.get('target_dir', '?')} "
        f"({result.get('skills_written', 0)} skills)"
    )


@ws_app.command("file")
def ws_file(
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
    read: bool = typer.Option(False, "--read", help="Read file content"),
    write: str | None = typer.Option(
        None, "--write", help="Write content (pass '-' to read from stdin)"
    ),
    file_path: str = typer.Option(
        "CLAUDE.md", "--path", help="File path within workspace"
    ),
) -> None:
    """Read or write a file in a workspace.

    Examples:
        workspaces file my-ws --read --path CLAUDE.md
        workspaces file my-ws --write "new content" --path AGENTS.md
    """
    if read and write is not None:
        console.print("[red]use --read or --write, not both[/red]")
        raise typer.Exit(2)
    if not read and write is None:
        console.print("[red]use --read or --write[/red]")
        raise typer.Exit(2)

    store = get_store()

    if read:
        try:
            result = workspaces_service.read_file_by_name(
                name, file_path, store=store, settings=get_settings()
            )
        except WorkspaceNotFound:
            console.print(f"[red]workspace {name!r} not found[/red]")
            raise typer.Exit(1)
        except Exception as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
        console.print(result.get("content", "") if result else "")
    elif write is not None:
        content = write
        if write == "-":
            content = sys.stdin.read()
        try:
            result = workspaces_service.write_file_by_name(
                name,
                file_path,
                content,
                store=store,
                settings=get_settings(),
            )
        except WorkspaceNotFound:
            console.print(f"[red]workspace {name!r} not found[/red]")
            raise typer.Exit(1)
        except Exception as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]written[/green] {file_path!r} ({result.get('bytes', 0)} bytes)")
