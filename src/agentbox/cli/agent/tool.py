"""Agent tools — ls, show, grant, revoke."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext, handle_cli_errors, resolve_agent

# TODO(cli-arch): AgentService.list_tool_catalog (core gap)
from agentbox.core.tools import SharedToolRegistry

tool_app = typer.Typer(
    name="tool",
    help="List, inspect, grant, and revoke agent tools.",
    no_args_is_help=True,
)


@tool_app.command("ls")
def tool_ls(
    ctx: typer.Context,
    agent_id: str | None = typer.Option(
        None, "--agent", "-a", help="Show tool grants for a specific agent"
    ),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    include_revoked: bool = typer.Option(
        False, "--include-revoked", help="Include revoked grants"
    ),
) -> None:
    """List registered agent tools.  Use --agent <id> to see grants."""
    obj: CLIContext = ctx.obj

    if agent_id is not None:
        resolve_agent(agent_id)
        items = obj.agents.list_tool_grants(agent_id, include_revoked=include_revoked)
        obj.render.agent.grants_table([dict(g) for g in items], agent_id)
        return

    specs = SharedToolRegistry.all()
    if tag:
        specs = [s for s in specs if tag in s.tags]

    obj.render.agent.tools_table(specs)


@tool_app.command("show")
def tool_show(
    ctx: typer.Context,
    tool_name: str = typer.Argument(..., help="Tool name"),
) -> None:
    """Show full details for a registered tool."""
    obj: CLIContext = ctx.obj
    spec = SharedToolRegistry.get(tool_name)
    if spec is None:
        obj.render.agent.error(f"Tool {tool_name!r} not found.")
        raise typer.Exit(1)

    obj.render.agent.tool_detail(spec)


@tool_app.command("grant")
def tool_grant(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to grant"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Grant a tool to an agent."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        obj.agents.grant_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    obj.render.agent.tool_granted(tool_name, agent_id)


@tool_app.command("revoke")
def tool_revoke(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to revoke"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Revoke a tool grant from an agent."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        obj.agents.revoke_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    obj.render.agent.tool_revoked(tool_name, agent_id)