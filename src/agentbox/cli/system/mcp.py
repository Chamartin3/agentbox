"""system mcp — show declared MCP servers and cached health."""

from __future__ import annotations

import json

import typer

from agentbox.cli.shared import CliCtx

mcp_app = typer.Typer(
    name="mcp",
    help="Show declared MCP servers and cached health.",
    no_args_is_help=True,
)


@mcp_app.command("ls")
def mcp_ls(ctx: typer.Context) -> None:
    """List MCP servers declared in the manifest with cached health."""
    obj: CliCtx = ctx.obj
    servers = obj.system.get_project_mcp_servers()

    if not servers:
        obj.render.system.mcp_servers_table([])
        return

    rows: list[tuple[str, str, str, str | None, bool, str | None]] = []
    for s in servers:
        if s.url:
            transport = s.transport or "http"
            endpoint = s.url
        elif s.command:
            transport = "stdio"
            endpoint = " ".join(s.command[:2]) + ("…" if len(s.command) > 2 else "")
        else:
            transport = "unknown"
            endpoint = "—"

        cache_path = obj.settings.mcp_cache_dir / f"{s.name}.json"
        tool_count: str | None = None
        is_cached: bool = False
        last_sync: str | None = None
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                tools = data.get("tools", [])
                tool_count = str(len(tools))
                last_sync = data.get("cached_at", "") or None
                is_cached = True
            except (json.JSONDecodeError, OSError):
                pass
        else:
            is_cached = False

        rows.append((s.name, transport, endpoint, tool_count, is_cached, last_sync))

    obj.render.system.mcp_servers_table(rows)
