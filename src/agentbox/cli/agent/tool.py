"""Agent tools — ls, show, grant, revoke."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext, handle_cli_errors, resolve_agent

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

    obj.render.agent.tools_table(obj.agents.list_tool_catalog(tag))


@tool_app.command("show")
def tool_show(
    ctx: typer.Context,
    tool_name: str = typer.Argument(..., help="Tool name"),
) -> None:
    """Show full details for a registered tool."""
    obj: CLIContext = ctx.obj
    spec = obj.agents.get_tool(tool_name)
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


@tool_app.command("forbid")
def tool_forbid(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to forbid"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Add a tool to an agent's deny-list."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        obj.agents.forbid_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    obj.render.agent.tool_forbidden(tool_name, agent_id)


@tool_app.command("unforbid")
def tool_unforbid(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    tool_name: str = typer.Argument(..., help="Tool name to unforbid"),
    changelog: str = typer.Option(..., "--changelog", help="Reason (min 3 chars)"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Remove a tool from an agent's deny-list."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        obj.agents.unforbid_tool(
            agent_id=agent_id,
            tool_name=tool_name,
            changelog=changelog,
            actor=actor,
        )
    obj.render.agent.tool_unforbidden(tool_name, agent_id)


@tool_app.command("effective")
def tool_effective(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    workspace_id: str | None = typer.Option(None, "--workspace", help="Workspace ID (optional)"),
) -> None:
    """List effective tools for an agent (after applying grants/forbids)."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    with handle_cli_errors():
        tools = obj.agents.list_effective_tools(agent_id, workspace_id)
    obj.render.agent.effective_tools_table(tools, agent_id, workspace_id)