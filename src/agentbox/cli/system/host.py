"""CLI sub-app: agentbox host-env — host-env profiles and workspace grants."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CliCtx

# TODO(cli-arch): WorkspaceService (plan 089)
from agentbox.core.service import (
    get_workspace_host_env,
    list_host_env_calls_for_run,
    list_host_env_profiles,
    resolve_workspace_host_env,
)

host_env_app = typer.Typer(
    name="host-env",
    help="Inspect host-env profiles, workspace grants, and run audit logs.",
    no_args_is_help=True,
)


@host_env_app.command("profiles")
def he_profiles(ctx: typer.Context) -> None:
    """List all host-env profiles."""
    obj: CliCtx = ctx.obj
    rows = list_host_env_profiles(obj.store)
    obj.render.system.host_env_profiles_table(rows)


@host_env_app.command("grants")
def he_grants(ctx: typer.Context, workspace_id: str) -> None:
    """Show the resolved host-env grants for a workspace."""
    obj: CliCtx = ctx.obj
    row = get_workspace_host_env(obj.store, workspace_id)
    if not row:
        obj.render.system.host_env_no_grants(workspace_id)
        return

    resolved = resolve_workspace_host_env(obj.store, workspace_id)
    obj.render.system.host_env_grants_view(workspace_id, row, resolved)


@host_env_app.command("audit")
def he_audit(ctx: typer.Context, run_id: str) -> None:
    """Show the host-env call audit log for a run."""
    obj: CliCtx = ctx.obj
    rows = list_host_env_calls_for_run(obj.store, run_id)
    obj.render.system.host_env_audit_table(rows, run_id)
