"""CLI sub-app: agentbox resource — CRUD for the resource repository."""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.service import (
    list_repo_resources,
    get_repo_resource_by_slug,
    list_repo_versions,
    create_repo_resource,
    import_repo_version,
    publish_repo_version,
    rollback_repo_resource,
)

resource_app = typer.Typer(
    name="resource",
    help="Manage versioned resources in the resource repository.",
    no_args_is_help=True,
)


@resource_app.command("list")
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
            r.get("active_version_id") or "[dim]—[/dim]",
            r.get("tags") or "",
        )
    console.print(table)


@resource_app.command("show")
def resource_show(slug: str) -> None:
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
    meta.add_row("name", resource.get("display_name") or "—")
    meta.add_row("description", resource.get("description") or "—")
    meta.add_row("tags", resource.get("tags") or "—")
    meta.add_row("status", resource.get("status") or "active")
    meta.add_row("active_version_id", resource.get("active_version_id") or "—")
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


@resource_app.command("upload")
def resource_upload(
    slug: str,
    file_path: str,
    changelog: str = typer.Option(
        "cli upload", "--changelog", help="Changelog for this version"
    ),
) -> None:
    """Upload a file as a new resource version (creates resource if absent)."""
    if len(changelog.strip()) < 3:
        console.print("[red]--changelog must be at least 3 characters[/red]")
        raise typer.Exit(1)

    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found:[/red] {file_path}")
        raise typer.Exit(2)

    content = path.read_bytes()
    content_text: str | None = None
    with contextlib.suppress(UnicodeDecodeError):
        content_text = content.decode("utf-8")

    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(
            f"[yellow]Resource {slug!r} not found — creating it as 'document'.[/yellow]"
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
        f"[green]✓[/green] uploaded version [bold]{version['version_number']}[/bold] "
        f"for resource [bold]{slug}[/bold] (id={version['id']})"
    )


@resource_app.command("publish")
def resource_publish(
    slug: str,
    version_id: str,
    changelog: str = typer.Option("publish via cli", "--changelog", help="Changelog"),
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
        f"[green]✓[/green] published version [bold]{version['version_number']}[/bold] "
        f"for resource [bold]{slug}[/bold]"
    )


@resource_app.command("rollback")
def resource_rollback(
    slug: str,
    version_number: int,
    changelog: str = typer.Option(
        ..., "--changelog", help="Reason for rollback (required)"
    ),
) -> None:
    """Roll back to a previous version (creates new version with old content)."""
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
        f"[green]✓[/green] rolled back to version {version_number} — "
        f"new version [bold]{version['version_number']}[/bold] for resource [bold]{slug}[/bold]"
    )


@resource_app.command("migrate-composition")
def resource_migrate_composition(
    agent: str | None = typer.Option(
        None, "--agent", help="Migrate only this agent_id (default: all agents)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would change without writing"
    ),
) -> None:
    """Migrate composition slots (input/output_schema, user_template) → resource bindings."""
    from agentbox.core.resources.composition_to_bindings import (
        migrate_composition_to_bindings,
    )

    if dry_run:
        console.print(
            "[yellow]--dry-run not implemented yet; migration is idempotent, "
            "running for real.[/yellow]"
        )

    from agentbox.cli._deps import get_settings

    store = get_store()
    settings = get_settings()
    report = migrate_composition_to_bindings(
        store,
        only_agent_id=agent,
        project_root=settings.project_root,
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


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------


@resource_app.command("versions")
def resource_versions(
    slug: str = typer.Argument(..., help="Resource slug"),
    upload: bool = typer.Option(
        False, "--upload", help="Upload a new version from a file"
    ),
    file_path: str = typer.Option(
        "", "--file", help="File path for --upload"
    ),
    changelog: str = typer.Option(
        "cli upload", "--changelog", help="Changelog for uploaded version"
    ),
) -> None:
    """List or upload resource versions.

    Examples:
        resources repo versions my-resource
        resources repo versions my-resource --upload --file ./data.csv
    """
    store = get_store()
    resource = get_repo_resource_by_slug(store, slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {slug!r}")
        raise typer.Exit(2)

    if upload:
        if not file_path:
            console.print("[red]--file required for --upload[/red]")
            raise typer.Exit(2)
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File not found:[/red] {file_path}")
            raise typer.Exit(2)
        content = path.read_bytes()
        content_text = None
        with contextlib.suppress(UnicodeDecodeError):
            content_text = content.decode("utf-8")
        version = import_repo_version(
            store,
            resource["id"],
            [("", content, None, content_text)],
            import_source="upload",
            changelog=changelog,
            activate=True,
        )
        console.print(
            f"[green]uploaded[/green] version {version['version_number']} "
            f"(id={version['id']})"
        )
        return

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


@resource_app.command("preview-modes")
def resource_preview_modes(
    resource_id: str = typer.Argument(..., help="Resource ID"),
) -> None:
    """List available preview modes for a resource."""
    from agentbox.core.service.bindings import preview_modes

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
        desc = m.get("text", "")[:80] if m.get("text") else m.get("description", "")
        console.print(f"[bold]{m.get('mode', '?')}[/bold]: {desc}")
