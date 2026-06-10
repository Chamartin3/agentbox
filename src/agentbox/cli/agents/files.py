"""Agent version files CLI command."""

from __future__ import annotations

import typer

from agentbox.cli._common import console
from agentbox.cli._deps import get_store
from agentbox.cli.agents.crud import agent_app
from agentbox.core.service.agents import (
    VersionFileNotFound,
    VersionNotDraft,
    VersionNotFound,
    delete_version_file,
    upload_version_file,
)


@agent_app.command("files")
def agent_files(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    add: bool = typer.Option(False, "--add", help="Add a file to the version"),
    rm: int | None = typer.Option(
        None, "--rm", help="File ID to remove from the version"
    ),
    kind: str | None = typer.Option(
        None, "--kind", help="File kind (output_schema, input_schema, etc.)"
    ),
    name: str | None = typer.Option(
        None, "--name", help="File name for --add"
    ),
    content: str | None = typer.Option(
        None, "--content", help="File content for --add"
    ),
) -> None:
    """Add or remove version bundle files.

    Examples:
        agents files my-agent 1 --add --kind output_schema --name schema.json --content '{"...""}'
        agents files my-agent 1 --rm 42
    """
    if add and rm is not None:
        console.print("[red]use --add or --rm, not both[/red]")
        raise typer.Exit(2)
    if not add and rm is None:
        console.print("[red]use --add or --rm[/red]")
        raise typer.Exit(2)

    store = get_store()

    if add:
        if not kind or not name or not content:
            console.print(
                "[red]--kind, --name, and --content required for --add[/red]"
            )
            raise typer.Exit(2)
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
    elif rm is not None:
        try:
            delete_version_file(
                store=store,
                agent_id=agent_id,
                version=version,
                file_id=rm,
            )
        except VersionNotFound:
            console.print(f"[red]version {version} not found[/red]")
            raise typer.Exit(1)
        except VersionNotDraft:
            console.print("[red]version is not a draft[/red]")
            raise typer.Exit(1)
        except VersionFileNotFound:
            console.print(f"[red]file {rm} not found[/red]")
            raise typer.Exit(1)
        console.print(f"[yellow]removed[/yellow] file {rm} from v{version}")
