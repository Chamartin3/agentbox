"""Work files — gen configs, gen skills, edit/read/write files."""

from __future__ import annotations

import sys

import typer

from agentbox.cli.shared import CLIContext
# TODO(cli-arch): WorkspaceService (plan 089)
from agentbox.core.service import workspaces as workspaces_service
# TODO(cli-arch): move to facade export
from agentbox.core.service.workspaces.errors import WorkspaceNotFound

file_app = typer.Typer(
    name="file",
    help="Generate configs, skills, and edit workspace files.",
    no_args_is_help=True,
)


@file_app.command("gen")
def file_gen(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
) -> None:
    """Generate runner configs into a workspace."""
    obj: CLIContext = ctx.obj
    try:
        result = workspaces_service.generate_configs_by_name(
            name, store=obj.store, settings=obj.settings,
        )
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)
    obj.render.workspace.configs_generated(result)


@file_app.command("skills")
def file_skills(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
) -> None:
    """Generate skill shell scripts into a workspace."""
    obj: CLIContext = ctx.obj
    try:
        result = workspaces_service.generate_skills_by_name(
            name, store=obj.store, settings=obj.settings,
        )
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)
    obj.render.workspace.skills_generated(result)


@file_app.command("edit")
def file_edit(
    ctx: typer.Context,
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
        work file edit my-ws --read --path CLAUDE.md
        work file edit my-ws --write "new content" --path AGENTS.md
    """
    obj: CLIContext = ctx.obj

    if read and write is not None:
        obj.render.workspace.file_edit_mutual_exclusive()
        raise typer.Exit(2)
    if not read and write is None:
        obj.render.workspace.file_edit_no_action()
        raise typer.Exit(2)

    if read:
        try:
            result = workspaces_service.read_file_by_name(
                name, file_path, store=obj.store, settings=obj.settings,
            )
        except WorkspaceNotFound:
            obj.render.workspace.workspace_not_found(name)
            raise typer.Exit(1)
        except Exception as exc:
            obj.render.workspace.error(str(exc))
            raise typer.Exit(1)
        obj.render.workspace.file_content(str(result.get("content", "")) if result else "")
    elif write is not None:
        content = write
        if write == "-":
            content = sys.stdin.read()
        try:
            result = workspaces_service.write_file_by_name(
                name, file_path, content, store=obj.store, settings=obj.settings,
            )
        except WorkspaceNotFound:
            obj.render.workspace.workspace_not_found(name)
            raise typer.Exit(1)
        except Exception as exc:
            obj.render.workspace.error(str(exc))
            raise typer.Exit(1)
        obj.render.workspace.file_written(file_path, int(result.get("bytes", 0)))
