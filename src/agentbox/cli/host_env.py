"""CLI sub-app: agentbox host-env — host-env profiles and workspace grants."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.api.deps import get_store
from agentbox.cli._common import console

host_env_app = typer.Typer(
    name="host-env",
    help="Inspect host-env profiles, workspace grants, and run audit logs.",
    no_args_is_help=True,
)


@host_env_app.command("profiles")
def he_profiles() -> None:
    """List all host-env profiles."""
    store = get_store()
    rows = store.list_host_env_profiles()
    if not rows:
        console.print("[yellow]No host-env profiles defined.[/yellow]")
        return

    table = Table(
        title="Host-env profiles",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Created at", style="dim")
    for r in rows:
        table.add_row(
            r["id"],
            r["name"],
            r.get("description") or "—",
            r.get("created_at") or "",
        )
    console.print(table)


@host_env_app.command("grants")
def he_grants(workspace_id: str) -> None:
    """Show the resolved host-env grants for a workspace."""
    store = get_store()
    row = store.get_workspace_host_env(workspace_id)
    if not row:
        console.print(f"[yellow]No host-env grant for workspace {workspace_id!r}.[/yellow]")
        return

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("workspace_id", workspace_id)
    meta.add_row("profile_id", row.get("profile_id") or "—")
    meta.add_row("changelog", row.get("changelog") or "—")
    meta.add_row("created_at", row.get("created_at") or "—")
    console.print(Panel(meta, title=f"Host-env grant — {workspace_id}", border_style="cyan"))

    resolved = store.resolve_workspace_host_env(workspace_id)
    grants = resolved.get("grants") or {}

    if grants:
        gtable = Table(header_style="bold green", padding=(0, 1))
        gtable.add_column("Capability", style="bold")
        gtable.add_column("Value")
        for cap, val in sorted(grants.items()):
            gtable.add_row(cap, str(val))
        console.print(Panel(gtable, title="Resolved grants", border_style="green"))
    else:
        console.print("[dim]No grants resolved.[/dim]")


@host_env_app.command("audit")
def he_audit(run_id: str) -> None:
    """Show the host-env call audit log for a run."""
    store = get_store()
    rows = store.list_host_env_calls_for_run(run_id)
    if not rows:
        console.print(f"[yellow]No host-env calls recorded for run {run_id!r}.[/yellow]")
        return

    table = Table(
        title=f"Host-env audit — run {run_id}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("ID", style="dim")
    table.add_column("Workspace", style="dim")
    table.add_column("Capability", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Error", style="red")
    table.add_column("Created at", style="dim")
    for r in rows:
        status = r.get("status") or ""
        status_display = "[green]ok[/green]" if status == "ok" else f"[red]{status}[/red]"
        table.add_row(
            r["id"],
            r.get("workspace_id") or "—",
            r["capability"],
            status_display,
            r.get("error") or "",
            r.get("created_at") or "",
        )
    console.print(table)
