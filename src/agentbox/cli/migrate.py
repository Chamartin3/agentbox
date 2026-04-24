from __future__ import annotations

import typer
from rich.table import Table
from rich.text import Text

from agentbox.api.deps import get_settings
from agentbox.cli._common import console
from agentbox.core.migrations import migrate_capabilities_to_manifest

migrate_app = typer.Typer(
    name="migrate",
    help="Migrate configurations between versions.",
    no_args_is_help=True,
)


@migrate_app.command("ws-perms")
def migrate_ws_perms() -> None:
    """Migrate workspace permissions from capabilities.json to agentbox.toml.

    Reads each workspace's permissions/capabilities.json and patches the
    corresponding [[workspaces]] block in the manifest. Original JSON files
    are backed up with a timestamp.
    """
    settings = get_settings()
    results = migrate_capabilities_to_manifest(settings.project_root)

    if not results:
        console.print("[yellow]No workspaces found or no migration needed.[/yellow]")
        return

    table = Table(
        title="Workspace Permissions Migration",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Workspace", style="bold")
    table.add_column("Migrated", justify="center")
    table.add_column("Backup", justify="center")

    for ws_name, result in results.items():
        migrated = (
            Text("✓", style="green") if result["migrated"] else Text("·", style="dim")
        )
        backed_up = (
            Text("✓", style="green") if result["backed_up"] else Text("·", style="dim")
        )
        table.add_row(ws_name, migrated, backed_up)

    console.print(table)
    migrated_count = sum(1 for r in results.values() if r["migrated"])
    console.print(
        f"\n[green]✓[/green] migrated [bold]{migrated_count}[/bold] workspace(s)"
    )
