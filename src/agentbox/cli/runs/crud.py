from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
import websockets
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentbox.api.deps import get_store
from agentbox.cli._common import console, event_color
from agentbox.core.data import read_transcript

runs_app = typer.Typer(
    name="runs",
    help="Inspect run history and transcripts.",
    no_args_is_help=True,
)


@runs_app.command("ls")
def runs_list(
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
    limit: int = typer.Option(20, "--limit", help="Max rows"),
) -> None:
    """Show recent runs with status, tokens, and cost."""
    store = get_store()
    rows = store.list_runs(limit=limit, agent_id=agent)
    if not rows:
        console.print("[yellow]No runs yet.[/yellow]")
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
    console.print(table)

    agg = store.aggregate_usage()
    console.print(
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
        console.print(f"[red]no such run[/red] {run_id!r}")
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
    console.print(Panel(meta, title="run", border_style="cyan"))

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
        console.print(Panel(u, title="usage", border_style="yellow"))

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
        console.print(Panel(gt, title="guardrails", border_style="magenta"))


@runs_app.command("tail")
def runs_tail(
    run_id: str,
    follow: bool = typer.Option(
        False, "--follow", help="Tail an in-progress run via WebSocket"
    ),
) -> None:
    """Replay a completed run's transcript."""
    if follow:
        _tail_follow(run_id)
        return

    store = get_store()
    rec = store.get_run(run_id)
    if rec is None:
        console.print(f"[red]no such run[/red] {run_id!r}")
        raise typer.Exit(2)

    if not rec.transcript_path:
        console.print("[yellow]no transcript for this run[/yellow]")
        return

    path = Path(rec.transcript_path)
    events = read_transcript(path)
    if not events:
        console.print("[yellow]transcript is empty[/yellow]")
        return

    for ev in events:
        t = ev.get("type", "?")
        style = event_color(t)
        console.print(f"[{style}][{t}][/{style}] {json.dumps(ev, default=str)[:400]}")


def _tail_follow(run_id: str) -> None:
    api = "http://localhost:8765"
    ws_url = api.replace("http", "ws") + f"/api/runs/{run_id}/stream"

    async def _run() -> None:
        async with websockets.connect(ws_url) as ws:
            async for msg in ws:
                ev = json.loads(msg)
                t = ev.get("type", "?")
                style = event_color(t)
                console.print(
                    f"[{style}][{t}][/{style}] {json.dumps(ev, default=str)[:400]}"
                )

    asyncio.run(_run())
