"""CLI sub-app: agentbox workspace-resources — workspace file binding management."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
from agentbox.cli.shared.deps import get_resource_service

workspace_resources_app = typer.Typer(
    name="workspace-resources",
    help="Manage workspace file resource bindings.",
    no_args_is_help=True,
)


@workspace_resources_app.command("ls")
def wr_list(
    ctx: typer.Context,
    workspace_id: str,
) -> None:
    """List all file bindings for a workspace."""
    obj: CLIContext = ctx.obj
    rows = obj.resources.list_workspace_file_bindings(workspace_id)
    obj.render.workspace.file_bindings_table(rows, workspace_id)


@workspace_resources_app.command("set")
def wr_set(
    ctx: typer.Context,
    workspace_id: str,
    dest_path: str,
    resource_slug: str,
    mode: str = typer.Option(
        "copy", "--mode", help="Materialize mode: copy|symlink|mount"
    ),
    reason: str = typer.Option(
        "", "--reason", "-r", help="Reason for change (min 3 chars)"
    ),
) -> None:
    """Add or replace a workspace file binding for a dest_path.

    Existing bindings are preserved; this target_path is upserted.
    """
    obj: CLIContext = ctx.obj
    if len(reason.strip()) < 3:
        obj.render.workspace.reason_required()
        raise typer.Exit(1)

    svc = get_resource_service()
    resource = svc.get_by_slug(resource_slug)
    if not resource:
        obj.render.workspace.resource_not_found(resource_slug)
        raise typer.Exit(2)

    existing = obj.resources.list_workspace_file_bindings(workspace_id)
    kept = [b for b in existing if b.get("target_path") != dest_path]
    new_binding: dict[str, object] = {
        "resource_id": resource["id"],
        "target_path": dest_path,
        "materialize_mode": mode,
        "on_conflict": "overwrite",
        "display_order": len(kept),
    }
    kept.append(new_binding)

    obj.resources.replace_workspace_file_bindings(workspace_id, kept, reason=reason)
    obj.render.workspace.file_binding_set(workspace_id, dest_path, resource_slug, mode)


@workspace_resources_app.command("check")
def wr_dry_run(
    ctx: typer.Context,
    workspace_id: str,
) -> None:
    """Preview what would be materialized for a workspace (no writes)."""
    obj: CLIContext = ctx.obj
    svc = get_resource_service()
    result = svc.dry_run_workspace_resources(workspace_id)
    entries = result.get("entries", [])
    conflicts = result.get("conflicts", [])
    obj.render.workspace.resources_resolution_table(
        entries, workspace_id, conflicts=conflicts,
    )
