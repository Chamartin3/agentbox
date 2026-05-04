"""CLI sub-app: agentbox workspace-resources — workspace file binding management."""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.api.deps import get_store
from agentbox.cli._common import console
from agentbox.core.run_prep import resolve_workspace_resources

workspace_resources_app = typer.Typer(
    name="workspace-resources",
    help="Manage workspace file resource bindings.",
    no_args_is_help=True,
)


@workspace_resources_app.command("list")
def wr_list(workspace_id: str) -> None:
    """List all file bindings for a workspace."""
    store = get_store()
    rows = store.list_workspace_file_bindings(workspace_id)
    if not rows:
        console.print(f"[yellow]No file bindings for workspace {workspace_id!r}.[/yellow]")
        return

    table = Table(
        title=f"Workspace file bindings — {workspace_id}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Order", style="dim")
    table.add_column("Target path", style="bold")
    table.add_column("Resource ID", style="dim")
    table.add_column("Mode", style="cyan")
    table.add_column("On conflict", style="dim")
    table.add_column("Pinned version", style="dim")
    for r in rows:
        table.add_row(
            str(r.get("display_order", 0)),
            r.get("target_path") or "—",
            r["resource_id"],
            r.get("materialize_mode") or "copy",
            r.get("on_conflict") or "error",
            r.get("pinned_version_id") or "—",
        )
    console.print(table)


@workspace_resources_app.command("set")
def wr_set(
    workspace_id: str,
    dest_path: str,
    resource_slug: str,
    mode: str = typer.Option("copy", "--mode", help="Materialize mode: copy|symlink|mount"),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for change (min 3 chars)"),
) -> None:
    """Add or replace a workspace file binding for a dest_path.

    Existing bindings are preserved; this target_path is upserted.
    """
    if len(reason.strip()) < 3:
        console.print("[red]--reason must be at least 3 characters[/red]")
        raise typer.Exit(1)

    store = get_store()
    resource = store.get_repo_resource_by_slug(resource_slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {resource_slug!r}")
        raise typer.Exit(2)

    existing = store.list_workspace_file_bindings(workspace_id)
    kept = [b for b in existing if b.get("target_path") != dest_path]
    new_binding = {
        "resource_id": resource["id"],
        "target_path": dest_path,
        "materialize_mode": mode,
        "on_conflict": "overwrite",
        "display_order": len(kept),
    }
    kept.append(new_binding)

    store.replace_workspace_file_bindings(workspace_id, kept, reason=reason)
    console.print(
        f"[green]✓[/green] binding set: workspace=[bold]{workspace_id}[/bold] "
        f"path=[bold]{dest_path}[/bold] → {resource_slug} (mode={mode})"
    )


@workspace_resources_app.command("dry-run")
def wr_dry_run(workspace_id: str) -> None:
    """Preview what would be materialized for a workspace (no writes)."""
    store = get_store()
    resolved = resolve_workspace_resources(store, workspace_id)
    if not resolved:
        console.print(f"[yellow]No workspace resource bindings for {workspace_id!r}.[/yellow]")
        return

    table = Table(
        title=f"Dry run — {workspace_id}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Target path", style="bold")
    table.add_column("Resource ID", style="dim")
    table.add_column("Version ID", style="dim")
    table.add_column("Mode", style="cyan")
    table.add_column("Blobs", justify="right", style="magenta")
    table.add_column("Content hash", style="dim")
    for r in resolved:
        table.add_row(
            r.get("target_path") or "—",
            r["resource_id"],
            r["version_id"],
            r.get("materialize_mode") or "copy",
            str(len(r.get("blobs") or [])),
            (r.get("content_hash") or "")[:12] + "…",
        )
    console.print(table)
    console.print(f"[dim]{len(resolved)} binding(s) would be materialized.[/dim]")
