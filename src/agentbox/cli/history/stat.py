"""History stats — usage, activity, runs, facets, stats."""

from __future__ import annotations

import json
from typing import Literal

import typer
from rich.json import JSON
from rich.table import Table

from agentbox.core.service.evaluation import ActivityRange, since_iso
from agentbox.core.service.evaluation.service import EvaluationService
from agentbox.cli.shared import console, get_store
import agentbox.core.service.execution as runs

stat_app = typer.Typer(
    name="stat",
    help="Run statistics: usage, activity, runs, facets, stats.",
    no_args_is_help=True,
)


@stat_app.command("usage")
def stat_usage() -> None:
    """Print the aggregate usage rollup as JSON."""
    data = EvaluationService().aggregate_usage()
    console.print(JSON(json.dumps(data, indent=2, default=str)))


@stat_app.command("activity")
def stat_activity(
    range_: ActivityRange = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
) -> None:
    """Print the activity summary as JSON."""
    data = EvaluationService().activity_summary(since_iso(range_), agent=agent)
    console.print(JSON(json.dumps(data, indent=2, default=str)))


@stat_app.command("runs")
def stat_runs(
    range_: ActivityRange = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
    executor: str | None = typer.Option(None, help="Filter by executor."),
    state: Literal["running", "ok", "error"] | None = typer.Option(
        None, help="Filter by state: running|ok|error."
    ),
    limit: int = typer.Option(50, help="Max rows to return."),
) -> None:
    """List enriched recent runs."""
    data = EvaluationService().list_runs_enriched(
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


@stat_app.command("facets")
def stat_facets() -> None:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    result = runs.run_facets(store=get_store())
    console.print(json.dumps(result, indent=2, default=str))


@stat_app.command("stats")
def stat_stats(
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
    status: str | None = typer.Option(None, "--status", help="Filter by status"),
    since: str | None = typer.Option(None, "--since", help="ISO start date"),
    until: str | None = typer.Option(None, "--until", help="ISO end date"),
) -> None:
    """Aggregated run statistics (alias for runs)."""
    result = runs.run_stats(
        store=get_store(),
        agent=agent, status=status, since=since, until=until,
    )
    console.print(json.dumps(result, indent=2, default=str))
