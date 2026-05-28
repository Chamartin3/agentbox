"""system project — manage project-level MCP server configuration."""

from __future__ import annotations

import json

import typer
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.data import McpServerSpec
from agentbox.core.service import (
    delete_project_mcp_server,
    get_project_mcp_servers,
    set_project_mcp_server,
)

project_app = typer.Typer(
    name="project",
    help="Manage project-level MCP servers.",
    no_args_is_help=True,
)


@project_app.command("mcp-servers")
def project_mcp_servers(
    ls: bool = typer.Option(True, "--ls", help="List MCP servers (default)"),
    set_: str | None = typer.Option(
        None, "--set", help="Add or update an MCP server (JSON config)"
    ),
    rm: str | None = typer.Option(
        None, "--rm", help="Remove an MCP server by name"
    ),
) -> None:
    """List, set, or remove project-level MCP servers.

    --set expects JSON: '{"url": "http://...", "transport": "http"}'
    """
    store = get_store()

    if rm is not None:
        result = delete_project_mcp_server(store, rm)
        if not result:
            console.print(f"[red]server {rm!r} not found[/red]")
            raise typer.Exit(1)
        console.print(f"[yellow]removed[/yellow] MCP server {rm!r}")
        return

    if set_ is not None:
        try:
            config = json.loads(set_)
        except json.JSONDecodeError as exc:
            console.print(f"[red]invalid JSON: {exc}[/red]")
            raise typer.Exit(2)
        name = config.pop("name", None) or "mcp"
        spec = McpServerSpec(
            name=name,
            url=config.get("url"),
            transport=config.get("transport", "http"),
            command=config.get("command"),
        )
        set_project_mcp_server(store, spec)
        console.print(f"[green]saved[/green] MCP server {name!r}")
        return

    servers = get_project_mcp_servers(store)
    if not servers:
        console.print("[dim]no project MCP servers configured[/dim]")
        return

    table = Table(title="Project MCP Servers", header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("URL")
    table.add_column("Transport")
    table.add_column("Command")
    for s in servers:
        url = s.url or s.command
        if url and isinstance(url, list):
            url = " ".join(url)
        table.add_row(
            s.name,
            str(url or "—"),
            s.transport or "http",
            " ".join(s.command) if s.command else "—",
        )
    console.print(table)
