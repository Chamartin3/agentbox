"""system project — manage project-level MCP server configuration."""

from __future__ import annotations

import json

import typer

from agentbox.cli.shared import CliCtx

# TODO(cli-arch): move to facade export (plan 095 Phase A)
from agentbox.core.service import McpServerSpec

project_app = typer.Typer(
    name="project",
    help="Manage project-level MCP servers.",
    no_args_is_help=True,
)


@project_app.command("mcp-servers")
def project_mcp_servers(
    ctx: typer.Context,
    ls: bool = typer.Option(True, "--ls", help="List MCP servers (default)"),
    set_: str | None = typer.Option(
        None, "--set", help="Add or update an MCP server (JSON config)"
    ),
    rm: str | None = typer.Option(
        None, "--rm", help="Remove an MCP server by name"
    ),
) -> None:
    """List, set, or remove project-level MCP servers.

    --set expects JSON: '{"url": "http://...", "transport": "http"}'
    """
    obj: CliCtx = ctx.obj

    if rm is not None:
        obj.system.delete_project_mcp_server(rm)
        obj.render.system.project_mcp_removed(rm)
        return

    if set_ is not None:
        try:
            config = json.loads(set_)
        except json.JSONDecodeError as exc:
            obj.render.system.error(f"invalid JSON: {exc}")
            raise typer.Exit(2)
        name = config.pop("name", None) or "mcp"
        spec = McpServerSpec(
            name=name,
            url=config.get("url"),
            transport=config.get("transport", "http"),
            command=config.get("command"),
        )
        obj.system.set_project_mcp_server(spec)
        obj.render.system.project_mcp_saved(name)
        return

    servers = obj.system.get_project_mcp_servers()
    obj.render.system.project_mcp_table(servers)
