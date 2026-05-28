"""agents grants — manage per-agent tool grants."""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console, resolve_agent
from agentbox.core.service import (
    grant_agent_tool,
    list_agent_tool_grants,
    revoke_agent_tool,
)

grants_app = typer.Typer(
    name="grants",
    help="Manage per-agent tool grants.",
    no_args_is_help=True,
)


@grants_app.command("ls")
def grants_ls(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    include_revoked: bool = typer.Option(
        False, "--include-revoked", help="Include revoked grants"
    ),
) -> None:
    """List tool grants for an agent."""
    resolve_agent(agent_id)
    store = get_store()
    items = list_agent_tool_grants(store, agent_id, include_revoked=include_revoked)
    if not items:
        console.print("[yellow]No tool grants.[/yellow]")
        return

    table = Table(title=f"Tool Grants — {agent_id}", header_style="bold cyan")
    table.add_column("Tool", style="bold")
    table.add_column("Revoked", justify="center")
    table.add_column("Changelog")
    table.add_column("Actor")
    table.add_column("Created")
    for g in items:
        revoked = "[red]yes[/red]" if g.get("revoked_at") else "[green]no[/green]"
        table.add_row(
            g.get("tool_name", ""),
            revoked,
            g.get("changelog", ""),
            g.get("actor", ""),
            g.get("created_at", ""),
        )
    console.print(table)


@grants_app.command("add")
def grants_add(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to grant"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Grant a tool to an agent."""
    resolve_agent(agent_id)
    store = get_store()
    try:
        grant_agent_tool(
            store,
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]granted[/green] {tool_name!r} to {agent_id!r}")


@grants_app.command("rm")
def grants_rm(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to revoke"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Revoke a tool grant from an agent."""
    resolve_agent(agent_id)
    store = get_store()
    try:
        revoke_agent_tool(
            store,
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[yellow]revoked[/yellow] {tool_name!r} from {agent_id!r}")
