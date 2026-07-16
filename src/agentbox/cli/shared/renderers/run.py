"""Run CLI renderer."""

from __future__ import annotations

import json as _json
from collections.abc import Sequence

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agentbox.core.data.jsontypes import RawJson
from agentbox.core.data.payload_types import EnrichedRunRow, UsagePayload
from agentbox.cli.shared.render import Renderer
from agentbox.core.service import RunCommentRow, UsageSummaryRow


class RunRenderer(Renderer):
    """Typed render methods for run contracts -- methods are added as the run branch migrates; formatting lives here, never in command bodies."""

    # ------------------------------------------------------------------
    # history ls -- runs table
    # ------------------------------------------------------------------

    def runs_table(self, rows: Sequence[RawJson]) -> None:
        """Render the 'history ls' runs table."""
        if not rows:
            self.warn("No runs yet.")
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
            # TODO(cli-arch): narrow untyped service dict at the contract level
            usage_raw = r.get("usage")
            usage: RawJson = usage_raw if isinstance(usage_raw, dict) else {}
            status_val = str(r.get("status", ""))
            status_style = {
                "ok": "green", "running": "blue", "error": "red",
            }.get(status_val, "white")
            status = Text(status_val, style=f"bold {status_style}")
            cost = usage.get("cost_usd")
            table.add_row(
                (str(r.get("id", "")))[:12],
                str(r.get("agent_id", "")),
                status,
                str(usage.get("input_tokens") or "\u00b7"),
                str(usage.get("output_tokens") or "\u00b7"),
                f"{cost:.4f}" if isinstance(cost, (int, float)) else "[dim]\u00b7[/dim]",
                str(r.get("created_at", "")),
                str(r.get("finished_at")) or "[dim]\u2026[/dim]",
            )
        self.print(table)

    # ------------------------------------------------------------------
    # history show -- run detail panels
    # ------------------------------------------------------------------

    def run_detail(self, run_dict: RawJson, usage: UsagePayload | None) -> None:
        """Render the 'history show' run detail panels."""
        meta = Table.grid(padding=(0, 2))
        meta.add_column(style="dim", justify="right")
        meta.add_column()
        meta.add_row("run id", str(run_dict.get("id", "")))
        meta.add_row("agent", str(run_dict.get("agent_id", "")))
        meta.add_row("status", str(run_dict.get("status", "")))
        meta.add_row("started", str(run_dict.get("created_at", "")))
        meta.add_row("finished", str(run_dict.get("finished_at") or "\u2014"))
        if run_dict.get("error"):
            meta.add_row("error", f"[red]{run_dict['error']}[/red]")
        self.con.print(Panel(meta, title="run", border_style="cyan"))

        if usage:
            u = Table.grid(padding=(0, 2))
            u.add_column(style="dim", justify="right")
            u.add_column()
            u.add_row("model", str(usage.get("model") or "\u2014"))
            u.add_row("input tokens", str(usage.get("input_tokens", 0)))
            u.add_row("output tokens", str(usage.get("output_tokens", 0)))
            u.add_row("cache read", str(usage.get("cache_read_tokens", 0)))
            u.add_row("cache write", str(usage.get("cache_write_tokens", 0)))
            cost = usage.get("cost_usd")
            u.add_row("cost", f"${cost:.4f}" if isinstance(cost, (int, float)) else "\u2014")
            self.con.print(Panel(u, title="usage", border_style="yellow"))

    # ------------------------------------------------------------------
    # usage aggregate
    # ------------------------------------------------------------------

    def usage_summary(self, agg: UsageSummaryRow) -> None:
        """Render the aggregate usage summary line."""
        self.dim(
            f"totals: "
            f"[cyan]{agg.get('input_tokens', 0)}[/cyan] in \u00b7 "
            f"[cyan]{agg.get('output_tokens', 0)}[/cyan] out \u00b7 "
            f"[yellow]${agg.get('cost_usd', 0):.4f}[/yellow] across "
            f"{agg.get('runs', 0)} run(s)"
        )

    # ------------------------------------------------------------------
    # history stat runs -- enriched runs table
    # ------------------------------------------------------------------

    def stats_table(self, results: Sequence[EnrichedRunRow]) -> None:
        """Render the 'history stat runs' table."""
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
                str(r.get("duration_ms", "") or "\u2014"),
            )
        self.print(table)

    # ------------------------------------------------------------------
    # history log -- event stream
    # ------------------------------------------------------------------

    def event_line(self, event_type: str, payload: RawJson) -> None:
        """Print a single event line with coloured event-type tag.

        Truncates the payload JSON to 400 characters for readability.
        """
        style = self.event_style(event_type)
        self.con.print(f"[{style}][{event_type}][/{style}] {_json.dumps(payload, default=str)[:400]}")

    def comments_list(self, items: Sequence[RunCommentRow]) -> None:
        """Render a list of run comments."""
        for c in items:
            self.con.print(
                f"[bold]{c.get('author', '')}[/bold] "
                f"[dim]{c.get('created_at', '')}[/dim]\n"
                f"  {c.get('body', '')}\n"
            )
