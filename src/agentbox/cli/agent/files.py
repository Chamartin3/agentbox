"""Agent version bundle files — add/remove files from a version."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.service.agents import (
    VersionFileNotFound,
    VersionNotDraft,
    VersionNotFound,
)

files_app = typer.Typer(
    name="files",
    help="Add or remove files in an agent version bundle.",
    no_args_is_help=True,
)


@files_app.command("add")
def files_add(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    kind: str = typer.Option(..., "--kind", help="File kind (output_schema, input_schema, etc.)"),
    name: str = typer.Option(..., "--name", help="File name"),
    content: str = typer.Option(..., "--content", help="File content"),
) -> None:
    """Add a file to a version."""
    obj: CLIContext = ctx.obj
    try:
        result = obj.agents.upload_version_file(
            agent_id=agent_id,
            version=version,
            kind=kind,
            name=name,
            content=content,
        )
    except VersionNotFound:
        obj.render.agent.error(f"version {version} not found")
        raise typer.Exit(1)
    except VersionNotDraft as exc:
        obj.render.agent.error(str(exc))
        raise typer.Exit(1)
    except Exception as exc:
        obj.render.agent.error(str(exc))
        raise typer.Exit(1)
    obj.render.agent.file_added(name, result["file"]["id"], result["sha256"])


@files_app.command("rm")
def files_rm(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number"),
    file_id: int = typer.Argument(..., help="File ID to remove"),
) -> None:
    """Remove a file from a version."""
    obj: CLIContext = ctx.obj
    try:
        obj.agents.remove_version_file(
            agent_id=agent_id,
            version=version,
            file_id=file_id,
        )
    except VersionNotFound:
        obj.render.agent.error(f"version {version} not found")
        raise typer.Exit(1)
    except VersionNotDraft:
        obj.render.agent.error("version is not a draft")
        raise typer.Exit(1)
    except VersionFileNotFound:
        obj.render.agent.error(f"file {file_id} not found")
        raise typer.Exit(1)
    obj.render.agent.file_removed(file_id, version)