"""agentbox CLI — `agentbox serve`, `agentbox run`, `agentbox agents`, ..."""

from __future__ import annotations

import asyncio
import json

import httpx
import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentbox.api.deps import get_loader, get_settings, get_store
from agentbox.core import workspaces as ws
from agentbox.core.migrations import migrate_capabilities_to_manifest

app = typer.Typer(help="agentbox — agent orchestration", rich_markup_mode="rich")
workspace_app = typer.Typer(help="Manage per-agent workspaces.")
runs_app = typer.Typer(help="Inspect run history.")
migrate_app = typer.Typer(help="Migrate configurations between versions.")
app.add_typer(workspace_app, name="workspace")
app.add_typer(runs_app, name="runs")
app.add_typer(migrate_app, name="migrate")

_console = Console()


def _resolve_agent(agent_id: str):
    a = get_loader().get(agent_id)
    if a is None:
        _console.print(f"[red]unknown agent[/red] {agent_id!r}")
        raise typer.Exit(2)
    return a


def _yn(b: bool) -> Text:
    return Text("✓", style="green") if b else Text("·", style="dim")


# ---------------------------------------------------------------------------
# serve / run
# ---------------------------------------------------------------------------


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the FastAPI server."""
    uvicorn.run("agentbox.api.app:app", host=host, port=port, log_level="info")


@app.command()
def run(
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
    _console.print(f"[dim]run_id={run_id}[/dim]")
    _console.print(
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
    import websockets  # local import; optional

    ws_url = api.replace("http", "ws") + f"/api/runs/{run_id}/stream"
    async with websockets.connect(ws_url) as ws:
        async for msg in ws:
            ev = json.loads(msg)
            t = ev.get("type", "?")
            style = {
                "text": "white",
                "log": "dim",
                "tool_call": "cyan",
                "tool_result": "green",
                "usage": "yellow",
                "guardrail": "magenta",
                "done": "bold",
            }.get(t, "white")
            _console.print(f"[{style}][{t}][/{style}] {json.dumps(ev)[:300]}")


# ---------------------------------------------------------------------------
# agents
# ---------------------------------------------------------------------------


@app.command()
def agents() -> None:
    """List agents declared in the project manifest."""
    rows = get_loader().load().agents
    if not rows:
        _console.print("[yellow]No agents declared.[/yellow] Create an agentbox.toml at the project root.")
        return

    table = Table(
        title="Agents",
        title_style="bold",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Runner", style="cyan")
    table.add_column("Model", style="dim")
    table.add_column("Session", style="dim")
    table.add_column("Workspace", style="dim")
    table.add_column("Guardrails", justify="right", style="magenta")
    table.add_column("Description")

    for a in rows:
        ws_display = (
            "[yellow]<ephemeral>[/yellow]"
            if a.workspace == "<ephemeral>"
            else (a.workspace or "[dim]auto[/dim]")
        )
        table.add_row(
            a.id,
            a.runner.kind,
            a.runner.model or "-",
            a.session_mode,
            ws_display,
            str(len(a.guardrails)),
            a.description or "",
        )
    _console.print(table)


# ---------------------------------------------------------------------------
# workspace
# ---------------------------------------------------------------------------


@workspace_app.command("list")
def workspace_list() -> None:
    """List all configured agents and their workspaces."""
    rows = ws.list_all(get_loader(), get_settings())
    if not rows:
        _console.print("[yellow]No agents declared.[/yellow]")
        return

    table = Table(
        title="Workspaces",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("State", justify="center", width=7)
    table.add_column("Agent", style="bold")
    table.add_column("Path", style="dim")
    table.add_column("CLAUDE.md", justify="center")
    table.add_column("Skills", justify="right", style="magenta")

    for w in rows:
        if w.ephemeral:
            state = Text("EPH", style="bold yellow")
        elif w.exists:
            state = Text("OK", style="bold green")
        else:
            state = Text("NEW", style="bold blue")
        table.add_row(
            state,
            w.agent_id,
            str(w.path),
            _yn(w.has_claude_md),
            str(w.skill_count) if w.skill_count else "[dim]·[/dim]",
        )
    _console.print(table)
    _console.print(
        "[dim]Legend:[/dim] "
        "[bold green]OK[/bold green]=exists  "
        "[bold blue]NEW[/bold blue]=not created yet  "
        "[bold yellow]EPH[/bold yellow]=ephemeral (tmp per run)"
    )


@workspace_app.command("path")
def workspace_path(agent: str) -> None:
    """Print the absolute path of an agent's workspace."""
    a = _resolve_agent(agent)
    path, _eph = ws.resolve_path(a, get_settings())
    typer.echo(str(path))


@workspace_app.command("new")
def workspace_new(agent: str, scaffold: bool = True) -> None:
    """Create the workspace directory (and scaffold a starter CLAUDE.md)."""
    a = _resolve_agent(agent)
    path = ws.ensure(a, get_settings(), scaffold=scaffold)
    _console.print(f"[green]✓[/green] workspace ready: [bold]{path}[/bold]")


@workspace_app.command("reset")
def workspace_reset(
    agent: str,
    confirm: bool = typer.Option(False, "--yes", help="Confirm destructive op"),
) -> None:
    """Delete and recreate the workspace (drops everything inside)."""
    if not confirm:
        _console.print(
            "[red]refusing without --yes[/red] (this deletes the workspace contents)"
        )
        raise typer.Exit(2)
    a = _resolve_agent(agent)
    path = ws.reset(a, get_settings())
    _console.print(f"[yellow]↻[/yellow] reset: [bold]{path}[/bold]")


@workspace_app.command("edit")
def workspace_edit(
    agent: str,
    file: str = typer.Option("CLAUDE.md", help="File within workspace to open"),
) -> None:
    """Open a workspace file in $EDITOR (falls back to vi)."""
    import os
    import subprocess

    a = _resolve_agent(agent)
    path = ws.ensure(a, get_settings(), scaffold=True)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.call([editor, str(path / file)])


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------


@runs_app.command("list")
def runs_list(
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
    limit: int = typer.Option(20, "--limit", help="Max rows"),
) -> None:
    """Show recent runs with status, tokens, and cost."""
    store = get_store()
    rows = store.list_runs(limit=limit, agent_id=agent)
    if not rows:
        _console.print("[yellow]No runs yet.[/yellow]")
        return

    table = Table(
        title=f"Runs (latest {len(rows)})",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Run", style="dim")
    table.add_column("Agent", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("In", justify="right", style="cyan")
    table.add_column("Out", justify="right", style="cyan")
    table.add_column("Cost $", justify="right", style="yellow")
    table.add_column("Started", style="dim")
    table.add_column("Finished", style="dim")

    for r in rows:
        usage = store.get_usage(r.id) or {}
        status_style = {
            "ok": "green",
            "running": "blue",
            "error": "red",
        }.get(r.status, "white")
        status = Text(r.status, style=f"bold {status_style}")
        cost = usage.get("cost_usd")
        table.add_row(
            r.id[:12],
            r.agent_id,
            status,
            str(usage.get("input_tokens") or "·"),
            str(usage.get("output_tokens") or "·"),
            f"{cost:.4f}" if cost else "[dim]·[/dim]",
            r.created_at,
            r.finished_at or "[dim]…[/dim]",
        )
    _console.print(table)

    agg = store.aggregate_usage()
    _console.print(
        f"[dim]totals:[/dim] "
        f"[cyan]{agg['input_tokens']}[/cyan] in · "
        f"[cyan]{agg['output_tokens']}[/cyan] out · "
        f"[yellow]${agg['cost_usd']:.4f}[/yellow] across "
        f"{agg['runs']} run(s)"
    )


@runs_app.command("show")
def runs_show(run_id: str) -> None:
    """Show metadata, usage, and guardrail results for a single run."""
    store = get_store()
    rec = store.get_run(run_id)
    if rec is None:
        _console.print(f"[red]no such run[/red] {run_id!r}")
        raise typer.Exit(2)
    usage = store.get_usage(rec.id) or {}
    guards = store.list_guardrails(rec.id)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("run id", rec.id)
    meta.add_row("agent", rec.agent_id)
    meta.add_row("status", rec.status)
    meta.add_row("started", rec.created_at)
    meta.add_row("finished", rec.finished_at or "—")
    if rec.error:
        meta.add_row("error", f"[red]{rec.error}[/red]")
    _console.print(Panel(meta, title="run", border_style="cyan"))

    if usage:
        u = Table.grid(padding=(0, 2))
        u.add_column(style="dim", justify="right")
        u.add_column()
        u.add_row("model", str(usage.get("model") or "—"))
        u.add_row("input tokens", str(usage.get("input_tokens", 0)))
        u.add_row("output tokens", str(usage.get("output_tokens", 0)))
        u.add_row("cache read", str(usage.get("cache_read_tokens", 0)))
        u.add_row("cache write", str(usage.get("cache_write_tokens", 0)))
        cost = usage.get("cost_usd")
        u.add_row("cost", f"${cost:.4f}" if cost else "—")
        _console.print(Panel(u, title="usage", border_style="yellow"))

    if guards:
        gt = Table(header_style="bold magenta", padding=(0, 1))
        gt.add_column("#", style="dim", justify="right")
        gt.add_column("Guardrail")
        gt.add_column("Result", justify="center")
        gt.add_column("Message")
        for g in guards:
            ok = bool(g["ok"])
            result = Text("✓ ok", style="green") if ok else Text("✗ fail", style="red")
            gt.add_row(str(g["attempt"]), g["name"], result, (g["message"] or "")[:80])
        _console.print(Panel(gt, title="guardrails", border_style="magenta"))


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


@migrate_app.command("workspace-permissions")
def migrate_workspace_permissions() -> None:
    """Migrate workspace permissions from capabilities.json to agentbox.toml.

    Reads each workspace's permissions/capabilities.json and patches the
    corresponding [[workspaces]] block in the manifest. Original JSON files
    are backed up with a timestamp.

    See docs/plans/05-workspace-inlining.md for details.
    """
    settings = get_settings()
    results = migrate_capabilities_to_manifest(settings.project_root)

    if not results:
        _console.print("[yellow]No workspaces found or no migration needed.[/yellow]")
        return

    table = Table(
        title="Workspace Permissions Migration",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Workspace", style="bold")
    table.add_column("Migrated", justify="center")
    table.add_column("Backup", justify="center")

    for ws_name, result in results.items():
        migrated = Text("✓", style="green") if result["migrated"] else Text("·", style="dim")
        backed_up = Text("✓", style="green") if result["backed_up"] else Text("·", style="dim")
        table.add_row(ws_name, migrated, backed_up)

    _console.print(table)
    migrated_count = sum(1 for r in results.values() if r["migrated"])
    _console.print(
        f"\n[green]✓[/green] migrated [bold]{migrated_count}[/bold] workspace(s)"
    )


if __name__ == "__main__":
    app()
