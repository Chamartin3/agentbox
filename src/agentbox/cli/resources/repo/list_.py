"""CLI commands: resource list."""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.service import list_repo_resources


def register_list(app: typer.Typer) -> None:
    @app.command("list")
    def resource_list(
        type: str | None = typer.Option(None, "--type", help="Filter by resource type"),
        tag: str | None = typer.Option(
            None, "--tag", help="Filter by tag (substring match)"
        ),
        limit: int = typer.Option(50, "--limit", help="Max rows to return"),
    ) -> None:
        """List resources in the repository."""
        store = get_store()
        rows = list_repo_resources(store, type=type, limit=limit)
        if tag:
            rows = [r for r in rows if tag in (r.get("tags") or "")]
        if not rows:
            console.print("[yellow]No resources found.[/yellow]")
            return
        table = Table(
            title="Resources",
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Slug", style="bold")
        table.add_column("Type", style="cyan")
        table.add_column("Name")
        table.add_column("Status", style="dim")
        table.add_column("Active version", style="dim")
        table.add_column("Tags", style="magenta")
        for r in rows:
            table.add_row(
                r["slug"],
                r["type"],
                r.get("display_name") or "",
                r.get("status") or "active",
                r.get("active_version_id") or "[dim]\u2014[/dim]",
                r.get("tags") or "",
            )
        console.print(table)
