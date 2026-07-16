"""History CRUD -- ls, show, cancel."""

from __future__ import annotations

import asyncio
import json

import typer

from agentbox.cli.shared import CLIContext, get_executor
from agentbox.core.service.execution import RunNotFound


# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


def register_ls(parent: typer.Typer) -> None:
    @parent.command("ls")
    def runs_list(
        ctx: typer.Context,
        agent: str | None = typer.Option(None, "--agent", help="Filter by agent id"),
        limit: int = typer.Option(20, "--limit", help="Max rows"),
        json_output: bool = typer.Option(
            False, "--json", help="Output as JSON instead of a table"
        ),
    ) -> None:
        """Show recent runs with status, tokens, and cost."""
        obj: CLIContext = ctx.obj

        rows = obj.execution.list_run_summaries(limit=limit, agent_id=agent)

        if json_output:
            payload = [r.model_dump(mode="json") for r in rows]
            obj.render.run.print(json.dumps(payload, indent=2, default=str))
            return

        obj.render.run.runs_table(rows)

        agg = obj.evaluation.aggregate_usage()
        obj.render.run.usage_summary(agg)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def register_show(parent: typer.Typer) -> None:
    @parent.command("show")
    def runs_show(
        ctx: typer.Context,
        run_id: str,
        json_output: bool = typer.Option(
            False, "--json", help="Output as JSON instead of formatted panels"
        ),
    ) -> None:
        """Show metadata and usage for a single run."""
        obj: CLIContext = ctx.obj

        rec = obj.execution.get_run(run_id)
        if rec is None:
            obj.render.run.error(f"no such run {run_id!r}")
            raise typer.Exit(2)

        usage = obj.execution.get_usage(run_id)
        run_dict = rec.model_dump() if hasattr(rec, "model_dump") else dict(rec.__dict__)

        detail = {"run": run_dict, "usage": usage}

        if json_output:
            obj.render.run.print(json.dumps(detail, indent=2, default=str))
            return

        obj.render.run.run_detail(run_dict, usage)


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


def register_cancel(parent: typer.Typer) -> None:
    @parent.command("cancel")
    def runs_cancel(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Run ID"),
    ) -> None:
        """Cancel an in-progress run. Idempotent."""
        obj: CLIContext = ctx.obj

        async def _cancel() -> None:
            await obj.execution.cancel_run(run_id, executor=get_executor())

        try:
            asyncio.run(_cancel())
        except RunNotFound:
            obj.render.run.error(f"run {run_id!r} not found")
            raise typer.Exit(1)
        obj.render.run.warn(f"cancelled {run_id!r}")
