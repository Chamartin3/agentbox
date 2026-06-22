"""History logs — tail, transcript, prompt, comments, outcome."""

from __future__ import annotations

import asyncio
import json

import typer
import websockets

from agentbox.cli.shared import console, event_color, get_store
from agentbox.core.service.execution import runs
from agentbox.core.service.execution.runs import RunNotFound

log_app = typer.Typer(
    name="log",
    help="Inspect run logs: tail, transcript, prompt, comments, outcome.",
    no_args_is_help=True,
)


@log_app.command("tail")
def log_tail(
    run_id: str,
    follow: bool = typer.Option(
        False, "--follow", help="Tail an in-progress run via WebSocket"
    ),
) -> None:
    """Replay a completed run's transcript, or tail in-progress."""
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


@log_app.command("transcript")
def log_transcript(
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


@log_app.command("prompt")
def log_prompt(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """Show the rendered prompt for a completed run."""
    try:
        result = runs.get_run_prompt(run_id, store=get_store())
    except RunNotFound:
        console.print(f"[red]run {run_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(json.dumps(result, indent=2, default=str))


@log_app.command("comments")
def log_comments(
    run_id: str = typer.Argument(..., help="Run ID"),
    add: str | None = typer.Option(None, "--add", help="Add a comment (body text)"),
    author: str = typer.Option("cli", "--author", help="Comment author"),
) -> None:
    """List or add comments for a run."""
    if add:
        try:
            runs.add_comment(run_id, store=get_store(), author=author, body=add)
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


@log_app.command("outcome")
def log_outcome(
    run_id: str = typer.Argument(..., help="Run ID"),
    status: str = typer.Argument(..., help="Outcome status"),
    error_kind: str | None = typer.Option(
        None, "--error-kind", help="Error kind if applicable"
    ),
) -> None:
    """Record downstream post-processing outcome for a completed run."""
    try:
        runs.post_outcome(
            run_id, store=get_store(), status=status, error_kind=error_kind,
        )
    except RunNotFound:
        console.print(f"[red]run {run_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[green]outcome recorded[/green]: {status}")
