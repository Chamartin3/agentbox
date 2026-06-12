"""Activity analytics CLI — KPIs, recent runs."""

from __future__ import annotations

import json as _json
from typing import Literal

import typer
from rich.json import JSON
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.service.feedback import ActivityRange, enrich_recent_runs, summary

app = typer.Typer(
    name="activity",
    help="Activity KPIs and recent-run rollups.",
    no_args_is_help=True,
)


@app.command("summary")
def activity_summary(
    range_: ActivityRange = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
) -> None:
    """Print the activity summary as JSON."""
    data = summary(get_store(), range_=range_, agent=agent)
    console.print(JSON(_json.dumps(data, indent=2, default=str)))


@app.command("runs")
def activity_runs(
    range_: ActivityRange = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
    executor: str | None = typer.Option(None, help="Filter by executor."),
    # ponytail: plain str Literal, not constants.ActivityStateFilter — typer/click
    # renders Literal[StrEnum] choices by member NAME (RUNNING|OK|ERROR), which
    # would break the lowercase `--state ok` CLI contract. The API side uses the
    # shared alias (pydantic matches by value); the CLI keeps the value literals.
    state: Literal["running", "ok", "error"] | None = typer.Option(
        None, help="Filter by state: running|ok|error."
    ),
    limit: int = typer.Option(50, help="Max rows to return."),
) -> None:
    """List enriched recent runs."""
    data = enrich_recent_runs(
        get_store(),
        range_=range_,
        agent=agent,
        executor=executor,
        state=state,
        limit=limit,
    )
    results = data.get("results", [])
    if not results:
        console.print("[yellow]No runs found.[/yellow]")
        return
    table = Table(title="Recent Runs", header_style="bold cyan", padding=(0, 1))
    table.add_column("Run ID", style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Started", style="dim")
    table.add_column("Duration (ms)", justify="right", style="dim")
    for r in results:
        table.add_row(
            str(r.get("id", "")),
            str(r.get("action_name", "")),
            str(r.get("state", "")),
            str(r.get("started_at", "")),
            str(r.get("duration_ms", "") or "—"),
        )
    console.print(table)
