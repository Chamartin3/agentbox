"""History logs — tail, transcript, prompt, comments, outcome."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
import websockets

from agentbox.cli.shared import CLIContext
from agentbox.core.service.execution import RunNotFound

log_app = typer.Typer(
    name="log",
    help="Inspect run logs: tail, transcript, prompt, comments, outcome.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# transcript helpers
# ---------------------------------------------------------------------------


def _read_transcript_file(path_str: str | None) -> list[dict]:
    """Read a JSONL transcript file, returning parsed events."""
    if not path_str:
        return []
    p = Path(path_str)
    if not p.exists():
        return []
    events: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


# ---------------------------------------------------------------------------
# tail
# ---------------------------------------------------------------------------


@log_app.command("tail")
def log_tail(
    ctx: typer.Context,
    run_id: str,
    follow: bool = typer.Option(
        False, "--follow", help="Tail an in-progress run via WebSocket"
    ),
) -> None:
    """Replay a completed run's transcript, or tail in-progress."""
    obj: CLIContext = ctx.obj

    if follow:
        _tail_follow(obj, run_id)
        return

    rec = obj.execution.get_run(run_id)
    if rec is None:
        obj.render.run.error(f"no such run {run_id!r}")
        raise typer.Exit(2)

    events = _read_transcript_file(rec.transcript_path)
    if not events:
        obj.render.run.warn("transcript is empty")
        return

    for ev in events:
        t = str(ev.get("type", "?"))
        obj.render.run.event_line(t, ev)


def _tail_follow(obj: CLIContext, run_id: str) -> None:
    api = "http://localhost:8765"
    ws_url = api.replace("http", "ws") + f"/api/runs/{run_id}/stream"

    async def _run() -> None:
        async with websockets.connect(ws_url) as ws:
            async for msg in ws:
                ev = json.loads(msg)
                t = str(ev.get("type", "?"))
                obj.render.run.event_line(t, ev)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# transcript
# ---------------------------------------------------------------------------


@log_app.command("transcript")
def log_transcript(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """Show the transcript for a run."""
    obj: CLIContext = ctx.obj

    rec = obj.execution.get_run(run_id)
    if rec is None:
        obj.render.run.error(f"run {run_id!r} not found")
        raise typer.Exit(1)

    events = _read_transcript_file(rec.transcript_path)
    if not events:
        obj.render.run.dim("empty transcript")
        return

    for ev in events:
        t = str(ev.get("type", "?"))
        obj.render.run.event_line(t, ev)


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------


@log_app.command("prompt")
def log_prompt(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """Show the rendered prompt for a completed run."""
    obj: CLIContext = ctx.obj

    rec = obj.execution.get_run(run_id)
    if rec is None:
        obj.render.run.error(f"run {run_id!r} not found")
        raise typer.Exit(1)

    raw = obj.execution.get_run_prompt(run_id)
    fragments = json.loads(raw) if raw else []
    total = sum(int(f.get("size_bytes") or 0) for f in fragments)
    result = {"run_id": run_id, "fragments": fragments, "total_bytes": total}
    obj.render.run.print(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------


@log_app.command("comments")
def log_comments(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID"),
    add: str | None = typer.Option(None, "--add", help="Add a comment (body text)"),
    author: str = typer.Option("cli", "--author", help="Comment author"),
) -> None:
    """List or add comments for a run."""
    obj: CLIContext = ctx.obj

    if add:
        if obj.execution.get_run(run_id) is None:
            raise RunNotFound(run_id)
        obj.execution.add_run_comment(run_id, author=author, body=add)
        obj.render.run.success("comment added")
    else:
        if obj.execution.get_run(run_id) is None:
            raise RunNotFound(run_id)
        items = obj.execution.list_run_comments(run_id)
        obj.render.run.comments_list(items)


# ---------------------------------------------------------------------------
# outcome
# ---------------------------------------------------------------------------


@log_app.command("outcome")
def log_outcome(
    ctx: typer.Context,
    run_id: str = typer.Argument(..., help="Run ID"),
    status: str = typer.Argument(..., help="Outcome status"),
    error_kind: str | None = typer.Option(
        None, "--error-kind", help="Error kind if applicable"
    ),
) -> None:
    """Record downstream post-processing outcome for a completed run."""
    obj: CLIContext = ctx.obj

    rec = obj.execution.get_run(run_id)
    if rec is None:
        raise RunNotFound(run_id)
    obj.execution.set_run_post_outcome(
        run_id, ok=(status == "ok"), error_kind=error_kind,
    )
    obj.render.run.success(f"outcome recorded: {status}")
