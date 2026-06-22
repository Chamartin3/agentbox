"""History CRUD — ls, show, cancel."""

from __future__ import annotations

import asyncio
import json

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentbox.cli.shared import console, get_executor, get_store
from agentbox.core.service import aggregate_usage
from agentbox.core.service.execution import runs
from agentbox.core.service.execution.runs import RunNotFound

# ---------------------------------------------------------------------------
# ls
# ---------------------------------------------------------------------------


def register_ls(parent: typer.Typer) -> None:
    @parent.command("ls")
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
                "ok": "green", "running": "blue", "error": "red",
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


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def register_show(parent: typer.Typer) -> None:
    @parent.command("show")
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


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


def register_cancel(parent: typer.Typer) -> None:
    @parent.command("cancel")
    def runs_cancel(
        run_id: str = typer.Argument(..., help="Run ID"),
    ) -> None:
        """Cancel an in-progress run. Idempotent."""
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
