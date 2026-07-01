"""workspaces skills — list and show skills for a workspace."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.service.workspaces.errors import WorkspaceNotFound

skills_app = typer.Typer(
    name="skills",
    help="List and inspect workspace skills.",
    no_args_is_help=True,
)


@skills_app.command("ls")
def skills_ls(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
) -> None:
    """List skills for a workspace."""
    obj: CLIContext = ctx.obj
    try:
        result = obj.workspaces.list_skills(name, settings=obj.settings)
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)

    items = result.get("skills", [])
    obj.render.workspace.skills_list(items)


@skills_app.command("show")
def skills_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
    skill_name: str = typer.Argument(..., help="Skill name"),
) -> None:
    """Show full skill content."""
    obj: CLIContext = ctx.obj
    try:
        result = obj.workspaces.get_skill_content(name, skill_name, settings=obj.settings)
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)

    if result is None:
        obj.render.workspace.skill_not_found(skill_name)
        raise typer.Exit(1)

    obj.render.workspace.skill_content(str(result.get("content", "")))
