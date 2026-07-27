"""mat import — load agents and skills from disk into the DB."""

from __future__ import annotations

from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.data.payload_types import ImportAction

app = typer.Typer(no_args_is_help=True)


@app.command("agent")
def import_agent(
    ctx: typer.Context,
    src: Path = typer.Argument(..., help="Directory containing the agent file(s)"),
) -> None:
    """Import an agent from disk into the DB (dedup-safe)."""
    obj: CLIContext = ctx.obj
    try:
        report = obj.materialization.import_agent(src)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    for o in report["outcomes"]:
        if o["action"] is ImportAction.collision_skipped:
            collision = o.get("collision_with", "unknown")
            typer.echo(f"  skip {o['item_id']}: checksum matches {collision}")
        else:
            typer.echo(f"  {o['action'].value}: {o['item_id']} v{o.get('version', '?')}")


@app.command("skill")
def import_skill(
    ctx: typer.Context,
    src: Path = typer.Argument(..., help="Directory containing the skill files"),
) -> None:
    """Import a skill directory from disk into the DB."""
    obj: CLIContext = ctx.obj
    try:
        report = obj.materialization.import_skill(src)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    for o in report["outcomes"]:
        typer.echo(f"  {o['action'].value}: {o['item_id']} v{o.get('version', '?')}")
