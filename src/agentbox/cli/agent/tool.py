"""Agent tools — ls, show, grant, revoke."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli.shared import console, handle_cli_errors, resolve_agent, get_store
from agentbox.core.service import (
    grant_agent_tool,
    list_agent_tool_grants,
    revoke_agent_tool,
)
from agentbox.core.tools import SharedToolRegistry

tool_app = typer.Typer(
    name="tool",
    help="List, inspect, grant, and revoke agent tools.",
    no_args_is_help=True,
)


@tool_app.command("ls")
def tool_ls(
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Show tool grants for a specific agent"
    ),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    include_revoked: bool = typer.Option(
        False, "--include-revoked", help="Include revoked grants"
    ),
) -> None:
    """List registered agent tools.  Use --agent <id> to see grants."""
    store = get_store()

    if agent_id is not None:
        resolve_agent(agent_id)
        items = list_agent_tool_grants(
            store, agent_id, include_revoked=include_revoked
        )
        if not items:
            console.print("[yellow]No tool grants.[/yellow]")
            return

        table = Table(
            title=f"Tool Grants — {agent_id}", header_style="bold cyan"
        )
        table.add_column("Tool", style="bold")
        table.add_column("Revoked", justify="center")
        table.add_column("Changelog")
        table.add_column("Actor")
        table.add_column("Created")
        for g in items:
            revoked = (
                "[red]yes[/red]" if g.get("revoked_at") else "[green]no[/green]"
            )
            table.add_row(
                g.get("tool_name", ""),
                revoked,
                g.get("changelog", ""),
                g.get("actor", ""),
                g.get("created_at", ""),
            )
        console.print(table)
        return

    specs = SharedToolRegistry.all()
    if tag:
        specs = [s for s in specs if tag in s.tags]

    if not specs:
        console.print("[yellow]No tools registered.[/yellow]")
        return

    table = Table(title="Agent Tools", header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Capability")
    table.add_column("Tags")
    for s in specs:
        table.add_row(s.name, s.capability, ", ".join(s.tags))
    console.print(table)


@tool_app.command("show")
def tool_show(
    tool_name: str = typer.Argument(..., help="Tool name"),
) -> None:
    """Show full details for a registered tool."""
    spec = SharedToolRegistry.get(tool_name)
    if spec is None:
        console.print(f"[red]Tool {tool_name!r} not found.[/red]")
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]{spec.name}[/bold]\n{spec.description}", title="Description"
        )
    )
    console.print(f"Capability: [cyan]{spec.capability}[/cyan]")
    console.print(f"Tags: {', '.join(spec.tags)}")

    input_schema = spec.input_model.model_json_schema()
    console.print(
        Panel(
            Syntax(str(input_schema), "json", theme="ansi_dark"),
            title="Input Schema",
        )
    )

    output_schema = spec.output_model.model_json_schema()
    console.print(
        Panel(
            Syntax(str(output_schema), "json", theme="ansi_dark"),
            title="Output Schema",
        )
    )


@tool_app.command("grant")
def tool_grant(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to grant"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Grant a tool to an agent."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        grant_agent_tool(
            store,
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    console.print(f"[green]granted[/green] {tool_name!r} to {agent_id!r}")


@tool_app.command("revoke")
def tool_revoke(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to revoke"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Revoke a tool grant from an agent."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        revoke_agent_tool(
            store,
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    console.print(f"[yellow]revoked[/yellow] {tool_name!r} from {agent_id!r}")
