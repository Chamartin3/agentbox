from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import typer
import uvicorn
import websockets
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentbox.cli._deps import get_loader as _DefinitionLoaderShim
from agentbox.cli._deps import get_store
from agentbox.cli._common import console, event_color
from agentbox.config import load_settings
from agentbox.core.engines.render import ConfigGenerator
from agentbox.core.service import get_project_mcp_servers
from agentbox.core.workspace.mcp.client import McpRegistry

app = typer.Typer(
    name="agentbox",
    help="Agent orchestration — serve, exec, doctor, and introspection commands",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the FastAPI server."""
    uvicorn.run("agentbox.api.app:app", host=host, port=port, log_level="info")


# ---------------------------------------------------------------------------
# exec  (renamed from run)
# ---------------------------------------------------------------------------


@app.command("exec")
def exec_cmd(
    agent: str,
    input_: str = typer.Argument(..., metavar="INPUT"),
    api: str = "http://localhost:8765",
    session_id: str | None = None,
    follow: bool = True,
) -> None:
    """POST a run to the API and stream its events."""
    body = {"agent": agent, "input": input_, "session_id": session_id}
    resp = httpx.post(f"{api}/api/runs", json=body, timeout=30)
    resp.raise_for_status()
    run_id = resp.json()["run_id"]
    console.print(f"[dim]run_id={run_id}[/dim]")
    console.print(
        Panel.fit(
            f"View: [link={api}/runs/{run_id}]{api}/runs/{run_id}[/link]",
            border_style="cyan",
        )
    )
    if not follow:
        typer.echo(run_id)
        return
    asyncio.run(_stream(api, run_id))


async def _stream(api: str, run_id: str) -> None:
    ws_url = api.replace("http", "ws") + f"/api/runs/{run_id}/stream"
    async with websockets.connect(ws_url) as ws:
        async for msg in ws:
            ev = json.loads(msg)
            t = ev.get("type", "?")
            style = event_color(t)
            console.print(f"[{style}][{t}][/{style}] {json.dumps(ev)[:300]}")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Run a suite of diagnostic checks and print the results."""
    settings = load_settings()
    table = Table(
        title="Agentbox Doctor",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 2),
    )
    table.add_column("Status", justify="center", width=8)
    table.add_column("Check", style="bold")
    table.add_column("Detail")

    failures = 0

    def _ok(check: str, detail: str = "") -> None:
        table.add_row(Text("OK", style="bold green"), check, detail)

    def _warn(check: str, detail: str) -> None:
        table.add_row(Text("WARN", style="bold yellow"), check, detail)

    def _fail(check: str, detail: str) -> None:
        nonlocal failures
        failures += 1
        table.add_row(Text("FAIL", style="bold red"), check, detail)

    # 1. Manifest exists
    path = settings.manifest_path
    if path.exists():
        _ok("Manifest exists", str(path))
    else:
        _fail("Manifest exists", f"not found at {path}")

    # 2. Manifest parses
    loader = _DefinitionLoaderShim()
    try:
        manifest = loader.load()
        _ok(
            "Manifest parses",
            f"{len(manifest.agents)} agent(s), {len(manifest.workspaces)} workspace(s)",
        )
    except Exception as exc:
        _fail("Manifest parses", str(exc))

    # 3. All workspaces resolvable
    try:
        from agentbox.cli._deps import get_store as _gs
        from agentbox.core import workspaces as ws

        rows = ws.list_all(_gs(), settings)
        resolvable = True
        for w in rows:
            if not w.exists and not w.ephemeral:
                resolvable = False
                _warn("Workspaces", f"{w.agent_id}: path {w.path} does not exist")
        if resolvable:
            _ok("Workspaces", f"{len(rows)} agent(s), all paths resolvable")
    except Exception as exc:
        _fail("Workspaces", str(exc))

    # 4. DB reachable
    try:
        store = get_store()
        store.list_runs(limit=1)
        _ok("Database", str(settings.db_path))
    except Exception as exc:
        _fail("Database", str(exc))

    # 5. Plugins loadable
    try:
        from agentbox.core.engines.backends.registry import backends as plugins

        backend_count = len(plugins.backends())
        _ok(
            "Plugins",
            f"{backend_count} backend(s)",
        )
    except Exception as exc:
        _fail("Plugins", str(exc))

    # 6. Generated configs fresh
    try:
        mcp_registry = McpRegistry(settings.mcp_cache_dir)
        mcp_server_name = "mcp"
        mcp_command = ["mcp_serve.sh"]
        servers = get_project_mcp_servers(store)
        if servers:
            srv = servers[0]
            mcp_server_name = srv.name
            if srv.command:
                mcp_command = srv.command

        gen = ConfigGenerator(
            agentbox_toml=settings.manifest_path,
            mcp_manifest=mcp_registry.manifest,
            mcp_server_name=mcp_server_name,
            mcp_command=mcp_command,
            verbose=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            gen.generate_configs_into(Path(tmp))
        _ok("Generated configs", "dry-run succeeded")
    except Exception as exc:
        _warn("Generated configs", str(exc))

    # 7. MCP cache present
    cache = settings.mcp_cache_dir
    if cache.exists():
        files = list(cache.glob("*.json"))
        _ok("MCP cache", f"{len(files)} cached server(s) in {cache}")
    else:
        _warn("MCP cache", f"cache dir {cache} does not exist")

    console.print(table)
    raise typer.Exit(min(failures, 1))


