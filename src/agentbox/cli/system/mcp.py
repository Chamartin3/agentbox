from __future__ import annotations

import json

import typer
from rich.table import Table

from agentbox.api.deps import get_store
from agentbox.cli._common import console
from agentbox.config import load_settings

mcp_app = typer.Typer(
    name="mcp",
    help="Show declared MCP servers and cached health.",
    no_args_is_help=True,
)


@mcp_app.command("ls")
def mcp_ls() -> None:
    """List MCP servers declared in the manifest with cached health."""
    settings = load_settings()
    servers = get_store().get_project_mcp_servers()

    if not servers:
        console.print("[yellow]No MCP servers configured.[/yellow]")
        return

    table = Table(
        title="MCP Servers",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Server")
    table.add_column("Transport")
    table.add_column("Endpoint / Command")
    table.add_column("Tools", justify="right")
    table.add_column("Status")
    table.add_column("Last sync")

    for s in servers:
        if s.url:
            transport = s.transport
            endpoint = s.url
        elif s.command:
            transport = "stdio"
            endpoint = " ".join(s.command[:2]) + ("…" if len(s.command) > 2 else "")

        # Try to read cache for health info
        cache_path = settings.mcp_cache_dir / f"{s.name}.json"
        status_str = "[dim]unknown[/dim]"
        tool_count = "?"
        last_sync = "—"
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                tools = data.get("tools", [])
                tool_count = str(len(tools))
                cached_at = data.get("cached_at", "")
                if cached_at:
                    last_sync = cached_at
                status_str = "[green]ok[/green]"
            except (json.JSONDecodeError, OSError):
                status_str = "[red]unavailable[/red]"
        else:
            status_str = "[dim]unknown[/dim]"

        table.add_row(s.name, transport, endpoint, tool_count, status_str, last_sync)

    console.print(table)
