"""workspaces skills — list and show skills for a workspace."""

from __future__ import annotations

import typer
from rich.syntax import Syntax

from agentbox.cli.shared import console, get_settings, get_store
from agentbox.core.service import workspaces as workspaces_service
from agentbox.core.service.workspaces.errors import WorkspaceNotFound

skills_app = typer.Typer(
    name="skills",
    help="List and inspect workspace skills.",
    no_args_is_help=True,
)


@skills_app.command("ls")
def skills_ls(
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
) -> None:
    """List skills for a workspace."""
    store = get_store()
    try:
        result = workspaces_service.list_skills_by_name(
            name,
            store=store,
            settings=get_settings(),
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)

    items = result.get("skills", [])
    if not items:
        console.print("[dim]no skills[/dim]")
        return

    for s in items:
        console.print(
            f"[bold]{s.get('name', '?')}[/bold]"
            + (f"  [dim]{s.get('description', '')}[/dim]" if s.get("description") else "")
        )


@skills_app.command("show")
def skills_show(
    name: str = typer.Argument(..., help="Workspace name or agent ID"),
    skill_name: str = typer.Argument(..., help="Skill name"),
) -> None:
    """Show full skill content."""
    store = get_store()
    try:
        result = workspaces_service.get_skill_content_by_name(
            name,
            skill_name,
            store=store,
            settings=get_settings(),
        )
    except WorkspaceNotFound:
        console.print(f"[red]workspace {name!r} not found[/red]")
        raise typer.Exit(1)

    if result is None:
        console.print(f"[red]skill {skill_name!r} not found[/red]")
        raise typer.Exit(1)

    content = result.get("content", "")
    if content:
        console.print(Syntax(content, "markdown", theme="ansi_dark"))
    else:
        console.print("[dim]empty skill[/dim]")
