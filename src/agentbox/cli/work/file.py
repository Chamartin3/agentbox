"""Work files — gen configs, gen skills, edit/read/write files."""

from __future__ import annotations

import sys

import typer

from agentbox.cli.shared import CLIContext
# TODO(cli-arch): move to facade export
from agentbox.core.data.errors import WorkspaceNotFound

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
        result = obj.workspaces.generate_configs(
            name, settings=obj.settings,
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
        result = obj.workspaces.generate_skills(name, settings=obj.settings)
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
            result = obj.workspaces.read_workspace_file(name, file_path, settings=obj.settings)
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
            result = obj.workspaces.write_workspace_file(name, file_path, content, settings=obj.settings)
        except WorkspaceNotFound:
            obj.render.workspace.workspace_not_found(name)
            raise typer.Exit(1)
        except Exception as exc:
            obj.render.workspace.error(str(exc))
            raise typer.Exit(1)
        obj.render.workspace.file_written(file_path, int(result.get("bytes", 0)))
