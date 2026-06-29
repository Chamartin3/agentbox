"""CLI sub-app: agentbox mcp-workspace — workspace MCP override management."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
# TODO(cli-arch): workspace MCP surface belongs on WorkspaceService (plan 089)
from agentbox.cli.shared import get_mcp_registry
# TODO(cli-arch): WorkspaceService (plan 089)
from agentbox.core.service import (
    SystemService,
    get_workspace_mcp_policy,
    get_workspace_mcp_tools,
    list_workspace_mcp_server_overrides,
    list_workspace_mcp_tool_overrides,
    set_workspace_mcp_policy,
    set_workspace_mcp_server_override,
)

mcp_workspace_app = typer.Typer(
    name="mcp-workspace",
    help="Manage workspace MCP server overrides and policies.",
    no_args_is_help=True,
)


@mcp_workspace_app.command("show")
def mcp_show(
    ctx: typer.Context,
    workspace_id: str,
) -> None:
    """Show MCP policy and server overrides for a workspace."""
    obj: CLIContext = ctx.obj
    servers = SystemService().get_project_mcp_servers()

    policy = get_workspace_mcp_policy(obj.store, workspace_id)
    server_overrides = list_workspace_mcp_server_overrides(obj.store, workspace_id)
    tool_overrides = list_workspace_mcp_tool_overrides(obj.store, workspace_id)

    obj.render.workspace.mcp_config_panel(workspace_id, policy, len(servers))
    obj.render.workspace.mcp_server_overrides_table(server_overrides)
    if tool_overrides:
        obj.render.workspace.mcp_tool_overrides_table(tool_overrides)


@mcp_workspace_app.command("policy")
def mcp_policy(
    ctx: typer.Context,
    workspace_id: str,
    policy_name: str,
    reason: str | None = typer.Option(
        None, "--reason", "-r", help="Reason (unused, for logging)"
    ),
) -> None:
    """Set the default MCP policy for a workspace."""
    obj: CLIContext = ctx.obj
    try:
        result = set_workspace_mcp_policy(obj.store, workspace_id, policy_name)
    except ValueError as exc:
        obj.render.workspace.invalid_policy(str(exc))
        raise typer.Exit(1) from exc
    obj.render.workspace.mcp_policy_set(result, workspace_id)


@mcp_workspace_app.command("toggle")
def mcp_toggle(
    ctx: typer.Context,
    workspace_id: str,
    server_name: str,
    on: bool = typer.Option(
        True, "--on/--off", help="Use --on to enable (default), --off to disable"
    ),
    reason: str = typer.Option(
        "", "--reason", "-r", help="Reason for change (min 3 chars)"
    ),
) -> None:
    """Enable or disable a specific MCP server for a workspace."""
    obj: CLIContext = ctx.obj
    if len(reason.strip()) < 3:
        obj.render.workspace.error("--reason must be at least 3 characters")
        raise typer.Exit(1)

    set_workspace_mcp_server_override(
        obj.store, workspace_id, server_name, enabled=on, changelog=reason
    )
    action = "enabled" if on else "disabled"
    obj.render.workspace.mcp_toggle(action, server_name, workspace_id)


@mcp_workspace_app.command("refresh")
def mcp_refresh(
    ctx: typer.Context,
    workspace_id: str,
) -> None:
    """Invalidate the MCP server cache for all servers in this workspace."""
    obj: CLIContext = ctx.obj
    overrides = list_workspace_mcp_server_overrides(obj.store, workspace_id)
    server_names = {o["server_name"] for o in overrides}
    for s in SystemService().get_project_mcp_servers():
        server_names.add(s.name)

    if not server_names:
        obj.render.workspace.no_mcp_servers(workspace_id)
        return

    registry = get_mcp_registry()
    cache_dir = obj.settings.mcp_cache_dir
    for name in sorted(server_names):
        cache_file = cache_dir / f"{name}.json"
        if cache_file.exists():
            cache_file.unlink()
            obj.render.workspace.mcp_cache_invalidated(name)
        else:
            obj.render.workspace.no_mcp_cache(name)
    # Force registry to re-discover on next request by resetting health map
    registry.reset_health()


@mcp_workspace_app.command("tools")
def mcp_tools(
    ctx: typer.Context,
    workspace_id: str,
) -> None:
    """List MCP tools available to a workspace."""
    obj: CLIContext = ctx.obj
    result = get_workspace_mcp_tools(workspace_id, store=obj.store, settings=obj.settings)
    obj.render.workspace.mcp_tools_table(result, workspace_id)
