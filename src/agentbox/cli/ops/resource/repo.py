"""Resource repo commands — list, show, upload, versions, publish, rollback, preview-modes, migrate-composition."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from agentbox.cli.shared import CliCtx
from agentbox.cli.shared.deps import get_resource_service  # TODO(cli-arch): ResourceService (plan 090)
from agentbox.core.resources.legacy_composition import migrate_composition_to_bindings  # TODO(cli-arch): ResourceService (plan 090)
from agentbox.core.service.resources.service import InvalidResource, ResourceNotFound

repo_app = typer.Typer(
    name="repo",
    help="Manage versioned resources in the repository.",
    no_args_is_help=True,
)


@repo_app.command("ls")
def repo_ls(
    ctx: typer.Context,
    type: str | None = typer.Option(None, "--type", help="Filter by resource type"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    limit: int = typer.Option(50, "--limit", help="Max rows to return"),
) -> None:
    """List resources in the repository."""
    obj: CliCtx = ctx.obj
    svc = get_resource_service()
    rows = svc.list_resources(type=type, limit=limit)["items"]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or "")]
    if not rows:
        obj.render.ops.warn("No resources found.")
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
    obj.render.ops.print(table)


@repo_app.command("show")
def repo_show(ctx: typer.Context, slug: str) -> None:
    """Show a resource and its version history."""
    obj: CliCtx = ctx.obj
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {slug!r}")
        raise typer.Exit(2)
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("id", resource["id"])
    meta.add_row("slug", resource["slug"])
    meta.add_row("type", resource["type"])
    meta.add_row("name", resource.get("display_name") or "---")
    meta.add_row("description", resource.get("description") or "---")
    obj.render.ops.panel(meta, title=f"Resource: {slug}", border="cyan")
    versions = svc.list_versions(resource["id"])["items"]
    if not versions:
        obj.render.ops.dim("No versions.")
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
    obj.render.ops.panel(vtable, title="Versions", border="green")


@repo_app.command("upload")
def repo_upload(
    ctx: typer.Context,
    slug: str,
    file_path: str,
    changelog: str = typer.Option("cli upload", "--changelog", help="Changelog"),
) -> None:
    """Upload a file as a new resource version."""
    obj: CliCtx = ctx.obj
    if len(changelog.strip()) < 3:
        obj.render.ops.error("--changelog must be at least 3 characters")
        raise typer.Exit(1)
    path = Path(file_path)
    if not path.exists():
        obj.render.ops.error(f"File not found: {file_path}")
        raise typer.Exit(2)
    content = path.read_bytes()
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.warn(f"Resource {slug!r} not found --- creating it as 'document'.")
        resource = svc.create_resource(slug=slug, type="document", display_name=slug)
    version = svc.import_upload_version(
        resource["id"],
        filename=path.name,
        content=content,
        mime_type=None,
        changelog=changelog,
    )
    obj.render.ops.success(f"uploaded version [bold]{version['version_number']}[/bold] for [bold]{slug}[/bold]")


@repo_app.command("log")
def repo_log(ctx: typer.Context, slug: str) -> None:
    """List versions for a resource."""
    obj: CliCtx = ctx.obj
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {slug!r}")
        raise typer.Exit(2)
    versions = svc.list_versions(resource["id"])["items"]
    if not versions:
        obj.render.ops.dim("No versions.")
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
    obj.render.ops.print(vtable)


@repo_app.command("publish")
def repo_publish(
    ctx: typer.Context,
    slug: str,
    version_id: str,
    changelog: str = typer.Option("publish via cli", "--changelog"),
) -> None:
    """Promote a draft version to active."""
    obj: CliCtx = ctx.obj
    if len(changelog.strip()) < 3:
        obj.render.ops.error("--changelog must be at least 3 characters")
        raise typer.Exit(1)
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {slug!r}")
        raise typer.Exit(2)
    try:
        version = svc.publish_version(resource["id"], version_id, reason=changelog)
    except (ResourceNotFound, InvalidResource) as exc:
        obj.render.ops.error(f"Publish failed: {exc}")
        raise typer.Exit(2)
    obj.render.ops.success(f"published version [bold]{version['version_number']}[/bold] for [bold]{slug}[/bold]")


@repo_app.command("rollback")
def repo_rollback(
    ctx: typer.Context,
    slug: str,
    version_number: int,
    changelog: str = typer.Option(..., "--changelog", help="Reason for rollback"),
) -> None:
    """Roll back to a previous version."""
    obj: CliCtx = ctx.obj
    if len(changelog.strip()) < 3:
        obj.render.ops.error("--changelog must be at least 3 characters")
        raise typer.Exit(1)
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {slug!r}")
        raise typer.Exit(2)
    try:
        version = svc.rollback_resource(
            resource["id"], target_version=version_number, reason=changelog
        )
    except (ResourceNotFound, InvalidResource) as exc:
        obj.render.ops.error(f"Rollback failed: {exc}")
        raise typer.Exit(2)
    obj.render.ops.success(f"rolled back to v{version_number} --- new v{version['version_number']} for [bold]{slug}[/bold]")


@repo_app.command("preview-modes")
def repo_preview_modes(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Resource ID"),
) -> None:
    """List available preview modes."""
    obj: CliCtx = ctx.obj
    svc = get_resource_service()
    try:
        result = svc.preview_modes(resource_id)
    except ResourceNotFound:
        obj.render.ops.error(f"resource {resource_id!r} not found")
        raise typer.Exit(1)
    modes = result.get("modes", [])
    if not modes:
        obj.render.ops.dim(f"No preview modes for resource {resource_id!r}")
        return
    for m in modes:
        obj.render.ops.info(
            f"[bold]{m.get('mode', '?')}[/bold]: {m.get('text', m.get('description', ''))[:80]}"
        )


@repo_app.command("migrate-composition")
def repo_migrate_composition(
    ctx: typer.Context,
    agent: str | None = typer.Option(
        None, "--agent", help="Migrate only this agent_id"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report without writing"),
) -> None:
    """Migrate composition slots to resource bindings."""
    obj: CliCtx = ctx.obj
    if dry_run:
        obj.render.ops.warn("--dry-run not implemented; running for real.")
    report = migrate_composition_to_bindings(
        obj.store, only_agent_id=agent, project_root=obj.settings.project_root
    )
    summary = report.summary()
    table = Table(
        title="Composition Migration", header_style="bold cyan", padding=(0, 2)
    )
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    for k, v in summary.items():
        table.add_row(k, str(v))
    obj.render.ops.print(table)
    if report.agents_migrated:
        obj.render.ops.success(f"migrated: {', '.join(report.agents_migrated)}")
    if report.failed:
        obj.render.ops.error("failed:")
        for agent_id, err in report.failed:
            obj.render.ops.error(f"  {agent_id}: {err}")
        raise typer.Exit(1)
