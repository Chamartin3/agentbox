"""Agent version bundle files — add/remove files from a version."""

from __future__ import annotations

import typer

from agentbox.cli.shared import console, get_store
from agentbox.core.service.agents import (
    VersionFileNotFound,
    VersionNotDraft,
    VersionNotFound,
    delete_version_file,
    upload_version_file,
)

files_app = typer.Typer(
    name="files",
    help="Add or remove files in an agent version bundle.",
    no_args_is_help=True,
)


@files_app.command("add")
def files_add(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    kind: str = typer.Option(..., "--kind", help="File kind (output_schema, input_schema, etc.)"),
    name: str = typer.Option(..., "--name", help="File name"),
    content: str = typer.Option(..., "--content", help="File content"),
) -> None:
    """Add a file to a version."""
    store = get_store()
    try:
        result = upload_version_file(
            store=store,
            agent_id=agent_id,
            version=version,
            kind=kind,
            name=name,
            content=content,
        )
    except VersionNotFound:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)
    except VersionNotDraft as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]added[/green] {name!r} (file_id={result['file']['id']}, "
        f"sha256={result['sha256'][:8]})"
    )


@files_app.command("rm")
def files_rm(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    file_id: int = typer.Argument(..., help="File ID to remove"),
) -> None:
    """Remove a file from a version."""
    store = get_store()
    try:
        delete_version_file(
            store=store,
            agent_id=agent_id,
            version=version,
            file_id=file_id,
        )
    except VersionNotFound:
        console.print(f"[red]version {version} not found[/red]")
        raise typer.Exit(1)
    except VersionNotDraft:
        console.print("[red]version is not a draft[/red]")
        raise typer.Exit(1)
    except VersionFileNotFound:
        console.print(f"[red]file {file_id} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[yellow]removed[/yellow] file {file_id} from v{version}")
