from __future__ import annotations

import typer
from rich.table import Table
from rich.text import Text

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.cli._common import console
from agentbox.core.migrations import migrate_capabilities_to_manifest
from agentbox.core.prompt.versioning.drift import _build_config_json

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


@migrate_app.command("to-db-only")
def migrate_to_db_only(agent_id: str) -> None:
    """Migrate a TOML-backed agent to DB-only management.

    Reads the active version's source TOML, copies content into the DB
    if not already there, flips sync_mode to 'off' and export_to_disk to
    True so the file becomes an export mirror rather than the source of truth.

    Idempotent: running twice will not create duplicate versions.
    """
    store = get_store()
    loader = get_loader()

    # Get active version
    active = store.get_active_version(agent_id)
    if active is None:
        console.print(
            f"[red]error:[/red] agent {agent_id!r} has no active version"
        )
        raise typer.Exit(1)

    # If config_json is empty, load the agent and populate it
    if not active.get("config_json"):
        agent = loader.get(agent_id)
        if agent is None:
            console.print(
                f"[red]error:[/red] could not load agent {agent_id!r} from manifest"
            )
            raise typer.Exit(1)

        # Rebuild the active version with config_json populated
        config_json_str = _build_config_json(agent)
        store.replace_version_config(active["id"], config_json_str)
        console.print(
            f"[cyan]info:[/cyan] populated config_json for v{active['version']}"
        )

    # Update agent_meta: sync_mode="off", export_to_disk=True
    result = store.update_agent_meta(agent_id, sync_mode="off", export_to_disk=True)
    if result is None:
        console.print(
            f"[red]error:[/red] agent_meta row not found for {agent_id!r}"
        )
        raise typer.Exit(1)

    console.print(
        f"[green]✓[/green] migrated {agent_id!r} to DB-only management"
    )
    console.print("  sync_mode: watch → off")
    console.print(f"  export_to_disk: {bool(result.get('export_to_disk'))}")


@migrate_app.command("prompt-versions")
def migrate_prompt_versions() -> None:
    """Backfill ``runs.prompt_version_id`` from historical prompt_versions.

    See ``agentbox.core.data.backfill_prompt_versions``.
    """
    from agentbox.core.data.backfill_prompt_versions import backfill

    store = get_store()
    n = backfill(store)
    console.print(f"[green]✓[/green] backfilled {n} run(s) with prompt_version_id")
