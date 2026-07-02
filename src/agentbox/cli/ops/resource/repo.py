"""Resource repo commands — list, show, upload, versions, publish, rollback, preview-modes, migrate-composition."""

from __future__ import annotations

from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext
from agentbox.cli.shared.deps import get_resource_service, get_db
from agentbox.core.constants import ResourceType
# TODO(cli-arch): ResourceService (plan 090)
from agentbox.core.resources.legacy_composition import migrate_composition_to_bindings  # TODO(cli-arch)
from agentbox.core.service.resources.service import InvalidResource, ResourceNotFound  # TODO(cli-arch)

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
    obj: CLIContext = ctx.obj
    svc = get_resource_service()
    rows = svc.list_resources(type=ResourceType(type) if type else None, limit=limit)["items"]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or "")]
    if not rows:
        obj.render.ops.warn("No resources found.")
        return
    obj.render.ops.resource_table(rows)


@repo_app.command("show")
def repo_show(ctx: typer.Context, slug: str) -> None:
    """Show a resource and its version history."""
    obj: CLIContext = ctx.obj
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {slug!r}")
        raise typer.Exit(2)
    versions = svc.list_versions(resource["id"])["items"]
    obj.render.ops.resource_detail(slug, resource, versions)


@repo_app.command("upload")
def repo_upload(
    ctx: typer.Context,
    slug: str,
    file_path: str,
    changelog: str = typer.Option("cli upload", "--changelog", help="Changelog"),
) -> None:
    """Upload a file as a new resource version."""
    obj: CLIContext = ctx.obj
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
        obj.render.ops.warn(
            f"Resource {slug!r} not found --- creating it as 'document'."
        )
        resource = svc.create_resource(slug=slug, type="document", display_name=slug)
    version = svc.import_upload_version(
        resource["id"],
        filename=path.name,
        content=content,
        mime_type=None,
        changelog=changelog,
    )
    obj.render.ops.success(
        f"uploaded version {version['version_number']} for {slug}"
    )


@repo_app.command("log")
def repo_log(ctx: typer.Context, slug: str) -> None:
    """List versions for a resource."""
    obj: CLIContext = ctx.obj
    svc = get_resource_service()
    resource = svc.get_by_slug(slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {slug!r}")
        raise typer.Exit(2)
    versions = svc.list_versions(resource["id"])["items"]
    if not versions:
        obj.render.ops.dim("No versions.")
        return
    obj.render.ops.version_table(versions)


@repo_app.command("publish")
def repo_publish(
    ctx: typer.Context,
    slug: str,
    version_id: str,
    changelog: str = typer.Option("publish via cli", "--changelog"),
) -> None:
    """Promote a draft version to active."""
    obj: CLIContext = ctx.obj
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
    obj.render.ops.success(
        f"published version {version['version_number']} for {slug}"
    )


@repo_app.command("rollback")
def repo_rollback(
    ctx: typer.Context,
    slug: str,
    version_number: int,
    changelog: str = typer.Option(..., "--changelog", help="Reason for rollback"),
) -> None:
    """Roll back to a previous version."""
    obj: CLIContext = ctx.obj
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
    obj.render.ops.success(
        f"rolled back to v{version_number} --- new v{version['version_number']} for {slug}"
    )


@repo_app.command("preview-modes")
def repo_preview_modes(
    ctx: typer.Context,
    resource_id: str = typer.Argument(..., help="Resource ID"),
) -> None:
    """List available preview modes."""
    obj: CLIContext = ctx.obj
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
        obj.render.ops.dim(
            f"{m.get('mode', '?')}: {m.get('text', m.get('description', ''))[:80]}"
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
    obj: CLIContext = ctx.obj
    if dry_run:
        obj.render.ops.warn("--dry-run not implemented; running for real.")
    settings = obj.settings
    db = get_db()
    report = migrate_composition_to_bindings(
        db.resources,
        db.resource_versions,
        db.agent_prompt_resource_bindings,
        db.agent_version_files,
        db.agent_versions,
        only_agent_id=agent,
        project_root=settings.project_root,
    )
    obj.render.ops.migration_composition_table(report.summary())
    if report.agents_migrated:
        obj.render.ops.success(f"migrated: {', '.join(report.agents_migrated)}")
    if report.failed:
        obj.render.ops.error("failed:")
        for agent_id, err in report.failed:
            obj.render.ops.error(f"  {agent_id}: {err}")
        raise typer.Exit(1)
