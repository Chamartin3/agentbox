"""Resource repo commands — list, show, upload, versions, publish, rollback, preview-modes, migrate-composition."""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.cli.shared import console, get_settings, get_store
from agentbox.core.resources.legacy_composition import migrate_composition_to_bindings
from agentbox.core.service import (
    create_repo_resource,
    get_repo_resource_by_slug,
    import_repo_version,
    list_repo_resources,
    list_repo_versions,
    publish_repo_version,
    rollback_repo_resource,
)
from agentbox.core.service.bindings import preview_modes

repo_app = typer.Typer(
    name="repo",
    help="Manage versioned resources in the repository.",
    no_args_is_help=True,
)


@repo_app.command("ls")
def repo_ls(
    type: str | None = typer.Option(None, "--type", help="Filter by resource type"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
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
        title="Resources", title_style="bold", header_style="bold cyan", padding=(0, 1)
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
            r.get("active_version_id") or "[dim]---[/dim]",
            r.get("tags") or "",
        )
    console.print(table)


@repo_app.command("show")
def repo_show(slug: str) -> None:
    """Show a resource and its version history."""
    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {slug!r}")
        raise typer.Exit(2)
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("id", resource["id"])
    meta.add_row("slug", resource["slug"])
    meta.add_row("type", resource["type"])
    meta.add_row("name", resource.get("display_name") or "---")
    meta.add_row("description", resource.get("description") or "---")
    console.print(Panel(meta, title=f"Resource: {slug}", border_style="cyan"))
    versions = list_repo_versions(store, resource["id"])
    if not versions:
        console.print("[dim]No versions.[/dim]")
        return
    vtable = Table(header_style="bold green", padding=(0, 1))
    vtable.add_column("#", style="dim")
    vtable.add_column("ID", style="dim")
    vtable.add_column("Draft", justify="center")
    vtable.add_column("Source")
    vtable.add_column("Changelog")
    vtable.add_column("Created at", style="dim")
    for v in versions:
        draft = (
            "[yellow]draft[/yellow]"
            if v.get("is_draft")
            else "[green]published[/green]"
        )
        vtable.add_row(
            str(v["version_number"]),
            v["id"],
            draft,
            v.get("import_source") or "",
            v.get("changelog") or "",
            v.get("created_at") or "",
        )
    console.print(Panel(vtable, title="Versions", border_style="green"))


@repo_app.command("upload")
def repo_upload(
    slug: str,
    file_path: str,
    changelog: str = typer.Option("cli upload", "--changelog", help="Changelog"),
) -> None:
    """Upload a file as a new resource version."""
    if len(changelog.strip()) < 3:
        console.print("[red]--changelog must be at least 3 characters[/red]")
        raise typer.Exit(1)
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        raise typer.Exit(2)
    content = path.read_bytes()
    content_text = None
    with contextlib.suppress(UnicodeDecodeError):
        content_text = content.decode("utf-8")
    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(
            f"[yellow]Resource {slug!r} not found --- creating it as 'document'.[/yellow]"
        )
        resource = create_repo_resource(store, slug, "document", slug)
    version = import_repo_version(
        store,
        resource["id"],
        [("", content, None, content_text)],
        import_source="upload",
        changelog=changelog,
        activate=True,
    )
    console.print(
        f"[green]uploaded[/green] version [bold]{version['version_number']}[/bold] for [bold]{slug}[/bold]"
    )


@repo_app.command("log")
def repo_log(slug: str) -> None:
    """List versions for a resource."""
    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {slug!r}")
        raise typer.Exit(2)
    versions = list_repo_versions(store, resource["id"])
    if not versions:
        console.print("[dim]No versions.[/dim]")
        return
    vtable = Table(header_style="bold green", padding=(0, 1))
    vtable.add_column("#", style="dim")
    vtable.add_column("ID", style="dim")
    vtable.add_column("Draft", justify="center")
    vtable.add_column("Source")
    vtable.add_column("Changelog")
    vtable.add_column("Created at", style="dim")
    for v in versions:
        draft = (
            "[yellow]draft[/yellow]"
            if v.get("is_draft")
            else "[green]published[/green]"
        )
        vtable.add_row(
            str(v["version_number"]),
            v["id"],
            draft,
            v.get("import_source") or "",
            v.get("changelog") or "",
            v.get("created_at") or "",
        )
    console.print(vtable)


@repo_app.command("publish")
def repo_publish(
    slug: str,
    version_id: str,
    changelog: str = typer.Option("publish via cli", "--changelog"),
) -> None:
    """Promote a draft version to active."""
    if len(changelog.strip()) < 3:
        console.print("[red]--changelog must be at least 3 characters[/red]")
        raise typer.Exit(1)
    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {slug!r}")
        raise typer.Exit(2)
    version = publish_repo_version(store, version_id, reason=changelog)
    console.print(
        f"[green]published[/green] version [bold]{version['version_number']}[/bold] for [bold]{slug}[/bold]"
    )


@repo_app.command("rollback")
def repo_rollback(
    slug: str,
    version_number: int,
    changelog: str = typer.Option(..., "--changelog", help="Reason for rollback"),
) -> None:
    """Roll back to a previous version."""
    if len(changelog.strip()) < 3:
        console.print("[red]--changelog must be at least 3 characters[/red]")
        raise typer.Exit(1)
    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {slug!r}")
        raise typer.Exit(2)
    version = rollback_repo_resource(
        store, resource["id"], version_number, reason=changelog
    )
    console.print(
        f"[green]rolled back[/green] to v{version_number} --- new v{version['version_number']} for [bold]{slug}[/bold]"
    )


@repo_app.command("preview-modes")
def repo_preview_modes(
    resource_id: str = typer.Argument(..., help="Resource ID"),
) -> None:
    """List available preview modes."""
    store = get_store()
    try:
        result = preview_modes(resource_id, store=store)
    except Exception:
        console.print(f"[red]resource {resource_id!r} not found[/red]")
        raise typer.Exit(1)
    modes = result.get("modes", [])
    if not modes:
        console.print(f"[dim]No preview modes for resource {resource_id!r}[/dim]")
        return
    for m in modes:
        console.print(
            f"[bold]{m.get('mode', '?')}[/bold]: {m.get('text', m.get('description', ''))[:80]}"
        )


@repo_app.command("migrate-composition")
def repo_migrate_composition(
    agent: str | None = typer.Option(
        None, "--agent", help="Migrate only this agent_id"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without writing"),
) -> None:
    """Migrate composition slots to resource bindings."""
    if dry_run:
        console.print("[yellow]--dry-run not implemented; running for real.[/yellow]")
    store = get_store()
    settings = get_settings()
    report = migrate_composition_to_bindings(
        store, only_agent_id=agent, project_root=settings.project_root
    )
    summary = report.summary()
    table = Table(
        title="Composition Migration", header_style="bold cyan", padding=(0, 2)
    )
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    for k, v in summary.items():
        table.add_row(k, str(v))
    console.print(table)
    if report.agents_migrated:
        console.print(f"[green]migrated:[/green] {', '.join(report.agents_migrated)}")
    if report.failed:
        console.print("[red]failed:[/red]")
        for agent_id, err in report.failed:
            console.print(f"  [red]{agent_id}[/red]: {err}")
        raise typer.Exit(1)
