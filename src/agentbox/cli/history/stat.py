"""History stats — usage, activity, runs, facets, stats."""

from __future__ import annotations

import json
from typing import Literal

import typer

# TODO(cli-arch): absorb into EvaluationService
from agentbox.core.service.evaluation import ActivityRange, since_iso

from agentbox.cli.shared import CLIContext

stat_app = typer.Typer(
    name="stat",
    help="Run statistics: usage, activity, runs, facets, stats.",
    no_args_is_help=True,
)


@stat_app.command("usage")
def stat_usage(ctx: typer.Context) -> None:
    """Print the aggregate usage rollup as JSON."""
    obj: CLIContext = ctx.obj
    data = obj.evaluation.aggregate_usage()
    obj.render.run.print(json.dumps(data, indent=2, default=str))


@stat_app.command("activity")
def stat_activity(
    ctx: typer.Context,
    range_: ActivityRange = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
) -> None:
    """Print the activity summary as JSON."""
    obj: CLIContext = ctx.obj
    data = obj.evaluation.activity_summary(since_iso(range_), agent=agent)
    obj.render.run.print(json.dumps(data, indent=2, default=str))


@stat_app.command("runs")
def stat_runs(
    ctx: typer.Context,
    range_: ActivityRange = typer.Option("30d", "--range", help="Time range."),
    agent: str | None = typer.Option(None, help="Filter by agent id."),
    executor: str | None = typer.Option(None, help="Filter by executor."),
    state: Literal["running", "ok", "error"] | None = typer.Option(
        None, help="Filter by state: running|ok|error."
    ),
    limit: int = typer.Option(50, help="Max rows to return."),
) -> None:
    """List enriched recent runs."""
    obj: CLIContext = ctx.obj
    data = obj.evaluation.list_runs_enriched(
        range_=range_,
        agent=agent,
        executor=executor,
        state=state,
        limit=limit,
    )
    results = data.get("results", [])
    if not results:
        obj.render.run.warn("No runs found.")
        return
    obj.render.run.stats_table(results)


@stat_app.command("facets")
def stat_facets(ctx: typer.Context) -> None:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    obj: CLIContext = ctx.obj
    result = {
        "agents": obj.evaluation.distinct_agent_ids(),
        "executors": obj.evaluation.distinct_executors(),
        "statuses": ["ok", "error", "failed", "timeout", "incomplete", "running"],
    }
    obj.render.run.print(json.dumps(result, indent=2, default=str))


@stat_app.command("stats")
def stat_stats(
    ctx: typer.Context,
    agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
    status: str | None = typer.Option(None, "--status", help="Filter by status"),
    since: str | None = typer.Option(None, "--since", help="ISO start date"),
    until: str | None = typer.Option(None, "--until", help="ISO end date"),
) -> None:
    """Aggregated run statistics (alias for runs)."""
    obj: CLIContext = ctx.obj
    result = obj.evaluation.stats_for_filters(
        agent_id=agent, status=status, since_iso=since, until_iso=until,
    )
    obj.render.run.print(json.dumps(result, indent=2, default=str))
