"""workspaces permissions — get/set workspace permissions."""

from __future__ import annotations

import json

import typer

from agentbox.cli.shared import CliCtx
# TODO(cli-arch): WorkspaceService (plan 089)
from agentbox.core.service import workspaces as workspaces_service
# TODO(cli-arch): move to facade export
from agentbox.core.service.workspaces.errors import WorkspaceNotFound

permissions_app = typer.Typer(
    name="permissions",
    help="Get or set workspace permissions.",
    no_args_is_help=True,
)


@permissions_app.command("get")
def permissions_get(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name"),
) -> None:
    """Show current permissions for a workspace."""
    obj: CliCtx = ctx.obj
    try:
        result = workspaces_service.get_permissions(
            name, store=obj.store, settings=obj.settings,
        )
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)

    obj.render.workspace.permissions_view(result, name)


@permissions_app.command("set")
def permissions_put(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Workspace name"),
    permissions_json: str = typer.Argument(
        ..., help="JSON permissions payload"
    ),
) -> None:
    """Set permissions for a workspace.

    Example:
        workspaces permissions put my-ws '{"allow": ["read"], "deny": []}'
    """
    obj: CliCtx = ctx.obj
    try:
        permissions = json.loads(permissions_json)
    except json.JSONDecodeError as exc:
        obj.render.workspace.invalid_json(str(exc))
        raise typer.Exit(2)

    try:
        workspaces_service.set_permissions(
            name, permissions, store=obj.store, settings=obj.settings,
        )
    except WorkspaceNotFound:
        obj.render.workspace.workspace_not_found(name)
        raise typer.Exit(1)
    obj.render.workspace.permissions_set(name)
