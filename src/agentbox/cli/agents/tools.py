"""agents tools — list and inspect shared agent tools."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli._common import console
from agentbox.core.tools.registry import SharedToolRegistry

tools_app = typer.Typer(
    name="tools",
    help="List and inspect registered agent tools.",
    no_args_is_help=True,
)


@tools_app.command("ls")
def tools_ls(
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
) -> None:
    """List registered agent tools."""
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


@tools_app.command("show")
def tools_show(
    tool_name: str = typer.Argument(..., help="Tool name"),
) -> None:
    """Show full details for a registered tool."""
    spec = SharedToolRegistry.get(tool_name)
    if spec is None:
        console.print(f"[red]Tool {tool_name!r} not found.[/red]")
        raise typer.Exit(1)

    console.print(
        Panel(f"[bold]{spec.name}[/bold]\n{spec.description}", title="Description")
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
