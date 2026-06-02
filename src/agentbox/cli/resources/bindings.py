"""CLI sub-app: agentbox prompt-bindings — manage agent prompt resource bindings."""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.agents.composition.resolver import resolve_prompt
from agentbox.core.run.run_prep import resolve_agent_prompt_bindings
from agentbox.core.service import (
    list_prompt_bindings,
    get_repo_resource_by_slug,
    replace_prompt_bindings,
    get_active_agent_version,
)

prompt_bindings_app = typer.Typer(
    name="prompt-bindings",
    help="Manage agent prompt resource bindings.",
    no_args_is_help=True,
)


@prompt_bindings_app.command("list")
def pb_list(agent_id: str) -> None:
    """List all prompt bindings for an agent."""
    store = get_store()
    rows = list_prompt_bindings(store, agent_id)
    if not rows:
        console.print(f"[yellow]No prompt bindings for agent {agent_id!r}.[/yellow]")
        return

    table = Table(
        title=f"Prompt bindings — {agent_id}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Order", style="dim")
    table.add_column("Marker", style="bold")
    table.add_column("Resource ID", style="dim")
    table.add_column("Mode", style="cyan")
    table.add_column("Required", justify="center")
    table.add_column("Pinned version", style="dim")
    for r in rows:
        required = "[green]✓[/green]" if r.get("required") else "[dim]·[/dim]"
        table.add_row(
            str(r.get("display_order", 0)),
            r["marker"],
            r["resource_id"],
            r.get("mode") or "",
            required,
            r.get("pinned_version_id") or "—",
        )
    console.print(table)


@prompt_bindings_app.command("set")
def pb_set(
    agent_id: str,
    marker: str,
    resource_slug: str,
    mode: str = typer.Option(
        "inline", "--mode", help="Binding mode: inline|skill_primer|name_only|manifest"
    ),
    reason: str = typer.Option(
        "", "--reason", "-r", help="Reason for change (min 3 chars)"
    ),
) -> None:
    """Add or replace a single prompt binding for an agent.

    The full binding list is replaced atomically: existing bindings are kept,
    this marker is upserted at the end.
    """
    if len(reason.strip()) < 3:
        console.print("[red]--reason must be at least 3 characters[/red]")
        raise typer.Exit(1)

    store = get_store()
    resource = get_repo_resource_by_slug(store, resource_slug)
    if not resource:
        console.print(f"[red]Resource not found:[/red] {resource_slug!r}")
        raise typer.Exit(2)

    existing = list_prompt_bindings(store, agent_id)
    # Upsert: remove any existing binding for this marker, append new one.
    kept = [b for b in existing if b["marker"] != marker]
    new_binding = {
        "resource_id": resource["id"],
        "marker": marker,
        "mode": mode,
        "required": True,
        "display_order": len(kept),
    }
    kept.append(new_binding)

    replace_prompt_bindings(store, agent_id, kept, reason=reason)
    console.print(
        f"[green]✓[/green] binding set: agent=[bold]{agent_id}[/bold] "
        f"marker=[bold]{marker}[/bold] → {resource_slug} (mode={mode})"
    )


@prompt_bindings_app.command("preview")
def pb_preview(agent_id: str) -> None:
    """Preview the resolved prompt for an agent with all bindings applied."""
    store = get_store()
    active = get_active_agent_version(store, agent_id)
    if not active:
        console.print(f"[red]No active version for agent {agent_id!r}[/red]")
        raise typer.Exit(2)

    prompt_content = active.get("prompt_content") or ""
    if not prompt_content:
        console.print(f"[yellow]Agent {agent_id!r} has no prompt content.[/yellow]")
        return

    resolved_bindings = resolve_agent_prompt_bindings(store, agent_id)
    resolution = resolve_prompt(prompt_content, resolved_bindings)

    if resolution.warnings:
        for w in resolution.warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")
    if resolution.unresolved_markers:
        console.print(
            f"[yellow]unresolved markers:[/yellow] {', '.join(resolution.unresolved_markers)}"
        )

    console.print(
        Panel(
            Syntax(resolution.rendered_prompt, "markdown", theme="ansi_dark"),
            title=f"Resolved prompt — {agent_id}",
            border_style="cyan",
        )
    )

    if resolution.snapshot:
        snap_table = Table(header_style="bold magenta", padding=(0, 1))
        snap_table.add_column("Marker")
        snap_table.add_column("Resource ID", style="dim")
        snap_table.add_column("Mode")
        snap_table.add_column("Version", style="dim")
        for rb in resolution.snapshot:
            snap_table.add_row(rb.marker, rb.resource_id, rb.mode, rb.version_id)
        console.print(Panel(snap_table, title="Binding snapshot", border_style="green"))
