from __future__ import annotations

import asyncio
import json

import typer
import websockets
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentbox.cli._deps import get_executor, get_store
from agentbox.cli._common import console, event_color
from agentbox.core.service.execution import runs
from agentbox.core.service.execution.runs import (
    RunNotFound,
)
from agentbox.core.service import aggregate_usage

runs_app = typer.Typer(
    name="runs",
    help="Inspect run history and transcripts.",
    no_args_is_help=True,
)


@runs_app.command("ls")
def runs_list(
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
    limit: int = typer.Option(20, "--limit", help="Max rows"),
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """Show recent runs with status, tokens, and cost."""
    rows = runs.list_runs(
        store=get_store(), agent=agent, limit=limit, with_usage=True
    )
    assert isinstance(rows, list)

    if json_output:
        console.print(json.dumps(rows, indent=2, default=str))
        return

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
        usage = r.get("usage") or {}
        status_style = {
            "ok": "green",
            "running": "blue",
            "error": "red",
        }.get(r.get("status", ""), "white")
        status = Text(r.get("status", ""), style=f"bold {status_style}")
        cost = usage.get("cost_usd")
        table.add_row(
            (r.get("id") or "")[:12],
            r.get("agent_id", ""),
            status,
            str(usage.get("input_tokens") or "·"),
            str(usage.get("output_tokens") or "·"),
            f"{cost:.4f}" if cost else "[dim]·[/dim]",
            r.get("created_at", ""),
            r.get("finished_at") or "[dim]…[/dim]",
        )
    console.print(table)

    store = get_store()
    agg = aggregate_usage(store=store)
    console.print(
        f"[dim]totals:[/dim] "
        f"[cyan]{agg['input_tokens']}[/cyan] in · "
        f"[cyan]{agg['output_tokens']}[/cyan] out · "
        f"[yellow]${agg['cost_usd']:.4f}[/yellow] across "
        f"{agg['runs']} run(s)"
    )


@runs_app.command("show")
def runs_show(
    run_id: str,
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of formatted panels"
    ),
) -> None:
    """Show metadata and usage for a single run."""
    try:
        detail = runs.get_run_detail(run_id, store=get_store())
    except RunNotFound:
        console.print(f"[red]no such run[/red] {run_id!r}")
        raise typer.Exit(2)

    if json_output:
        console.print(json.dumps(detail, indent=2, default=str))
        return

    run_dict = detail["run"]
    usage = detail.get("usage") or {}

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", justify="right")
    meta.add_column()
    meta.add_row("run id", run_dict.get("id"))
    meta.add_row("agent", run_dict.get("agent_id"))
    meta.add_row("status", run_dict.get("status"))
    meta.add_row("started", run_dict.get("created_at"))
    meta.add_row("finished", run_dict.get("finished_at") or "—")
    if run_dict.get("error"):
        meta.add_row("error", f"[red]{run_dict['error']}[/red]")
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
    try:
        events = runs.get_transcript(run_id, store=store)
    except RunNotFound:
        console.print(f"[red]no such run[/red] {run_id!r}")
        raise typer.Exit(2)

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


# ---------------------------------------------------------------------------
# Stats and facets
# ---------------------------------------------------------------------------


@runs_app.command("stats")
def runs_stats(
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
    status: str | None = typer.Option(None, "--status", help="Filter by status"),
    since: str | None = typer.Option(None, "--since", help="ISO start date"),
    until: str | None = typer.Option(None, "--until", help="ISO end date"),
) -> None:
    """Aggregated run statistics."""
    result = runs.run_stats(
        store=get_store(),
        agent=agent,
        status=status,
        since=since,
        until=until,
    )
    console.print(json.dumps(result, indent=2, default=str))


@runs_app.command("facets")
def runs_facets() -> None:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    result = runs.run_facets(store=get_store())
    console.print(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@runs_app.command("comments")
def runs_comments(
    run_id: str = typer.Argument(..., help="Run ID"),
    add: str | None = typer.Option(None, "--add", help="Add a comment (body text)"),
    author: str = typer.Option("cli", "--author", help="Comment author"),
) -> None:
    """List or add comments for a run."""
    if add:
        try:
            runs.add_comment(
                run_id, store=get_store(), author=author, body=add
            )
        except RunNotFound:
            console.print(f"[red]run {run_id!r} not found[/red]")
            raise typer.Exit(1)
        console.print("[green]comment added[/green]")
    else:
        try:
            result = runs.list_comments(run_id, store=get_store())
        except RunNotFound:
            console.print(f"[red]run {run_id!r} not found[/red]")
            raise typer.Exit(1)
        items = result.get("items", [])
        if not items:
            console.print("[dim]no comments[/dim]")
            return
        for c in items:
            console.print(
                f"[bold]{c.get('author', '')}[/bold] "
                f"[dim]{c.get('created_at', '')}[/dim]\n"
                f"  {c.get('body', '')}\n"
            )


# ---------------------------------------------------------------------------
# Prompt and transcript
# ---------------------------------------------------------------------------


@runs_app.command("prompt")
def runs_prompt(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """Show the rendered prompt for a completed run."""
    try:
        result = runs.get_run_prompt(run_id, store=get_store())
    except RunNotFound:
        console.print(f"[red]run {run_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(json.dumps(result, indent=2, default=str))


@runs_app.command("transcript")
def runs_transcript(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """Show the transcript for a run."""
    try:
        events = runs.get_transcript(run_id, store=get_store())
    except RunNotFound:
        console.print(f"[red]run {run_id!r} not found[/red]")
        raise typer.Exit(1)
    if not events:
        console.print("[dim]empty transcript[/dim]")
        return
    for ev in events:
        t = ev.get("type", "?")
        style = event_color(t)
        console.print(f"[{style}][{t}][/{style}] {json.dumps(ev, default=str)[:400]}")


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------


@runs_app.command("post-outcome")
def runs_post_outcome(
    run_id: str = typer.Argument(..., help="Run ID"),
    status: str = typer.Argument(..., help="Outcome status"),
    error_kind: str | None = typer.Option(
        None, "--error-kind", help="Error kind if applicable"
    ),
) -> None:
    """Record downstream post-processing outcome for a completed run."""
    try:
        runs.post_outcome(
            run_id,
            store=get_store(),
            status=status,
            error_kind=error_kind,
        )
    except RunNotFound:
        console.print(f"[red]run {run_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[green]outcome recorded[/green]: {status}")


@runs_app.command("cancel")
def runs_cancel(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """Cancel an in-progress run. Idempotent.

    Note: effective cancellation requires the executor to be running
    (i.e., the server is active). In CLI-only mode this sets the
    cancelled flag.
    """
    async def _cancel() -> None:
        try:
            await runs.cancel_run(
                run_id, store=get_store(), executor=get_executor()
            )
        except RunNotFound:
            console.print(f"[red]run {run_id!r} not found[/red]")
            raise typer.Exit(1)

    asyncio.run(_cancel())
    console.print(f"[yellow]cancelled[/yellow] {run_id!r}")
