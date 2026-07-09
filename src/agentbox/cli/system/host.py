"""CLI sub-app: agentbox host-env — host-env profiles and workspace grants."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext

host_env_app = typer.Typer(
    name="host-env",
    help="Inspect host-env profiles, workspace grants, and run audit logs.",
    no_args_is_help=True,
)


@host_env_app.command("profiles")
def he_profiles(ctx: typer.Context) -> None:
    """List all host-env profiles."""
    obj: CLIContext = ctx.obj
    rows = obj.workspaces.list_host_env_profiles()
    obj.render.system.host_env_profiles_table(rows)


@host_env_app.command("grants")
def he_grants(ctx: typer.Context, agent_id: str) -> None:
    """Show the resolved host-env grants for an agent."""
    obj: CLIContext = ctx.obj
    row = obj.workspaces.get_agent_host_env(agent_id)
    if not row:
        obj.render.system.host_env_no_grants(agent_id)
        return

    resolved = obj.workspaces.resolve_agent_host_env(agent_id)
    obj.render.system.host_env_grants_view(agent_id, row, resolved)


@host_env_app.command("audit")
def he_audit(ctx: typer.Context, run_id: str) -> None:
    """Show the host-env call audit log for a run."""
    obj: CLIContext = ctx.obj
    rows = obj.system.list_host_env_calls_for_run(run_id)
    obj.render.system.host_env_audit_table(rows, run_id)
