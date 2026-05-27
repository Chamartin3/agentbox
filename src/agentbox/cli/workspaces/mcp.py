"""CLI sub-app: agentbox mcp-workspace — workspace MCP override management."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.api.deps import get_store
from agentbox.cli._common import console
from agentbox.core.data import VALID_POLICIES

mcp_workspace_app = typer.Typer(
    name="mcp-workspace",
    help="Manage workspace MCP server overrides and policies.",
    no_args_is_help=True,
)


@mcp_workspace_app.command("show")
def mcp_show(workspace_id: str) -> None:
    """Show MCP policy and server overrides for a workspace."""
    store = get_store()
    servers = store.get_project_mcp_servers()

    policy = store.get_workspace_mcp_policy(workspace_id)
    server_overrides = store.list_workspace_mcp_server_overrides(workspace_id)
    tool_overrides = store.list_workspace_mcp_tool_overrides(workspace_id)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("workspace_id", workspace_id)
    meta.add_row("policy", f"[bold]{policy}[/bold]")
    meta.add_row("project_servers", str(len(servers)))
    console.print(Panel(meta, title="MCP workspace config", border_style="cyan"))

    if server_overrides:
        stable = Table(header_style="bold green", padding=(0, 1))
        stable.add_column("Server", style="bold")
        stable.add_column("Enabled", justify="center")
        stable.add_column("Changelog", style="dim")
        stable.add_column("Updated at", style="dim")
        for o in server_overrides:
            enabled = "[green]✓[/green]" if o.get("enabled") else "[red]✗[/red]"
            stable.add_row(
                o["server_name"],
                enabled,
                o.get("changelog") or "",
                o.get("created_at") or "",
            )
        console.print(Panel(stable, title="Server overrides", border_style="green"))
    else:
        console.print("[dim]No server overrides.[/dim]")

    if tool_overrides:
        ttable = Table(header_style="bold magenta", padding=(0, 1))
        ttable.add_column("Server", style="bold")
        ttable.add_column("Tool")
        ttable.add_column("Enabled", justify="center")
        for o in tool_overrides:
            enabled = "[green]✓[/green]" if o.get("enabled") else "[red]✗[/red]"
            ttable.add_row(o["server_name"], o["tool_name"], enabled)
        console.print(Panel(ttable, title="Tool overrides", border_style="magenta"))


@mcp_workspace_app.command("policy")
def mcp_policy(
    workspace_id: str,
    policy_name: str,
    reason: str | None = typer.Option(
        None, "--reason", "-r", help="Reason (unused, for logging)"
    ),
) -> None:
    """Set the default MCP policy for a workspace."""
    if policy_name not in VALID_POLICIES:
        console.print(
            f"[red]Invalid policy.[/red] Must be one of: {', '.join(VALID_POLICIES)}"
        )
        raise typer.Exit(1)

    store = get_store()
    result = store.set_workspace_mcp_policy(workspace_id, policy_name)
    console.print(
        f"[green]✓[/green] policy set to [bold]{result}[/bold] for workspace {workspace_id!r}"
    )


@mcp_workspace_app.command("enable")
def mcp_enable(
    workspace_id: str,
    server_name: str,
    reason: str = typer.Option(
        "", "--reason", "-r", help="Reason for change (min 3 chars)"
    ),
) -> None:
    """Enable a specific MCP server for a workspace."""
    if len(reason.strip()) < 3:
        console.print("[red]--reason must be at least 3 characters[/red]")
        raise typer.Exit(1)

    store = get_store()
    store.set_workspace_mcp_server_override(
        workspace_id, server_name, enabled=True, changelog=reason
    )
    console.print(
        f"[green]✓[/green] server [bold]{server_name}[/bold] enabled for workspace {workspace_id!r}"
    )


@mcp_workspace_app.command("disable")
def mcp_disable(
    workspace_id: str,
    server_name: str,
    reason: str = typer.Option(
        "", "--reason", "-r", help="Reason for change (min 3 chars)"
    ),
) -> None:
    """Disable a specific MCP server for a workspace."""
    if len(reason.strip()) < 3:
        console.print("[red]--reason must be at least 3 characters[/red]")
        raise typer.Exit(1)

    store = get_store()
    store.set_workspace_mcp_server_override(
        workspace_id, server_name, enabled=False, changelog=reason
    )
    console.print(
        f"[red]✗[/red] server [bold]{server_name}[/bold] disabled for workspace {workspace_id!r}"
    )


@mcp_workspace_app.command("refresh")
def mcp_refresh(workspace_id: str) -> None:
    """Invalidate the MCP server cache for all servers in this workspace."""
    store = get_store()

    overrides = store.list_workspace_mcp_server_overrides(workspace_id)
    server_names = {o["server_name"] for o in overrides}
    for s in store.get_project_mcp_servers():
        server_names.add(s.name)

    if not server_names:
        console.print(
            f"[yellow]No servers to refresh for workspace {workspace_id!r}.[/yellow]"
        )
        return

    from agentbox.api.deps import get_mcp_registry, get_settings

    registry = get_mcp_registry()
    settings = get_settings()
    cache_dir = settings.mcp_cache_dir
    for name in sorted(server_names):
        cache_file = cache_dir / f"{name}.json"
        if cache_file.exists():
            cache_file.unlink()
            console.print(f"[green]✓[/green] cache invalidated: {name}")
        else:
            console.print(f"[dim]no cache for: {name}[/dim]")
    # Force registry to re-discover on next request by resetting health map
    registry._health.clear()  # type: ignore[attr-defined]
