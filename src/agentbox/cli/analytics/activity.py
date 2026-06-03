"""Activity analytics CLI — KPIs, recent runs."""

from __future__ import annotations

import json as _json
from typing import Literal

import typer
from rich.json import JSON
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.execution.evaluate import activity as svc

app = typer.Typer(
    name="activity",
    help="Activity KPIs and recent-run rollups.",
    no_args_is_help=True,
)

_Range = Literal["7d", "30d", "90d"]


@app.command("summary")
def activity_summary(
    range_: _Range = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
) -> None:
    """Print the activity summary as JSON."""
    data = svc.summary(get_store(), range_=range_, agent=agent)
    console.print(JSON(_json.dumps(data, indent=2, default=str)))


@app.command("runs")
def activity_runs(
    range_: _Range = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
    executor: str | None = typer.Option(None, help="Filter by executor."),
    state: Literal["running", "ok", "error"] | None = typer.Option(
        None, help="Filter by state: running|ok|error."
    ),
    limit: int = typer.Option(50, help="Max rows to return."),
) -> None:
    """List enriched recent runs."""
    data = svc.enrich_recent_runs(
        get_store(),
        range_=range_,
        agent=agent,
        executor=executor,
        state=state,
        limit=limit,
    )
    runs = data.get("runs", [])
    if not runs:
        console.print("[yellow]No runs found.[/yellow]")
        return
    table = Table(title="Recent Runs", header_style="bold cyan", padding=(0, 1))
    table.add_column("Run ID", style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Started", style="dim")
    table.add_column("Duration (ms)", justify="right", style="dim")
    for r in runs:
        table.add_row(
            str(r.get("run_id", "")),
            str(r.get("agent_id", "")),
            str(r.get("status", "")),
            str(r.get("started_at", "")),
            str(r.get("duration_ms", "") or "—"),
        )
    console.print(table)
