"""mat export — write agents and environments to disk."""

from __future__ import annotations

from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.data.errors import AgentNotFound, WorkspaceNotFound
from agentbox.core.service.agent_formats import AgentFileFormat

app = typer.Typer(no_args_is_help=True)


@app.command("agent")
def export_agent(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID to export"),
    fmt: AgentFileFormat = typer.Option(..., "--format", "-f", help="claudecode|opencode|codex"),
    dest: Path = typer.Option(Path("."), "--dest", "-d", help="Destination directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Export an agent to disk in the given format."""
    obj: CLIContext = ctx.obj
    try:
        report = obj.materialization.export_agent(agent_id, fmt, dest, force=force)
    except (AgentNotFound, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    for f in report["files"]:
        typer.echo(f"  {f['action'].value}: {f['path']}")
    typer.echo(f"Exported {agent_id} → {report['dest']}")


@app.command("env")
def export_env(
    ctx: typer.Context,
    workspace_id: str = typer.Argument(..., help="Workspace ID or name"),
    dest: Path = typer.Option(Path("."), "--dest", "-d", help="Destination directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Export a workspace environment to disk."""
    obj: CLIContext = ctx.obj
    try:
        report = obj.materialization.export_environment(workspace_id, dest, force=force)
    except (WorkspaceNotFound, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    for f in report["files"]:
        typer.echo(f"  {f['action'].value}: {f['path']}")
    agents = ", ".join(report["agents"]) or "none"
    typer.echo(f"Exported workspace {workspace_id} ({agents}) → {report['dest']}")
