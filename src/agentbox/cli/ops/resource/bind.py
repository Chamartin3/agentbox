"""CLI sub-app: agentbox prompt-bindings — manage agent prompt resource bindings."""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.cli.shared import CliCtx
from agentbox.cli.shared.deps import get_resource_service  # TODO(cli-arch): ResourceService (plan 090)
from agentbox.core.service import (  # TODO(cli-arch): ResourceService (plan 090)
    get_active_agent_version,
    resolve_agent_prompt_bindings,
    resolve_prompt,
)

prompt_bindings_app = typer.Typer(
    name="prompt-bindings",
    help="Manage agent prompt resource bindings.",
    no_args_is_help=True,
)


@prompt_bindings_app.command("list")
def pb_list(ctx: typer.Context, agent_id: str) -> None:
    """List all prompt bindings for an agent."""
    obj: CliCtx = ctx.obj
    svc = get_resource_service()
    rows = svc.list_prompt_bindings_raw(agent_id)
    if not rows:
        obj.render.ops.warn(f"No prompt bindings for agent {agent_id!r}.")
        return

    table = Table(
        title=f"Prompt bindings \u2014 {agent_id}",
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
        required = "[green]\u2713[/green]" if r.get("required") else "[dim]\u00b7[/dim]"
        table.add_row(
            str(r.get("display_order", 0)),
            r["marker"],
            r["resource_id"],
            r.get("mode") or "",
            required,
            r.get("pinned_version_id") or "\u2014",
        )
    obj.render.ops.print(table)


@prompt_bindings_app.command("set")
def pb_set(
    ctx: typer.Context,
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
    obj: CliCtx = ctx.obj
    if len(reason.strip()) < 3:
        obj.render.ops.error("--reason must be at least 3 characters")
        raise typer.Exit(1)

    svc = get_resource_service()
    resource = svc.get_by_slug(resource_slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {resource_slug!r}")
        raise typer.Exit(2)

    existing = svc.list_prompt_bindings_raw(agent_id)
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

    svc.replace_prompt_bindings_raw(agent_id, kept, reason=reason)
    obj.render.ops.success(
        f"binding set: agent=[bold]{agent_id}[/bold] "
        f"marker=[bold]{marker}[/bold] \u2192 {resource_slug} (mode={mode})"
    )


@prompt_bindings_app.command("preview")
def pb_preview(ctx: typer.Context, agent_id: str) -> None:
    """Preview the resolved prompt for an agent with all bindings applied."""
    obj: CliCtx = ctx.obj
    active = get_active_agent_version(obj.store, agent_id)
    if not active:
        obj.render.ops.error(f"No active version for agent {agent_id!r}")
        raise typer.Exit(2)

    prompt_content = active.get("prompt_content") or ""
    if not prompt_content:
        obj.render.ops.warn(f"Agent {agent_id!r} has no prompt content.")
        return

    resolved_bindings = resolve_agent_prompt_bindings(obj.store, agent_id)
    resolution = resolve_prompt(prompt_content, resolved_bindings)

    if resolution.warnings:
        for w in resolution.warnings:
            obj.render.ops.warn(str(w))
    if resolution.unresolved_markers:
        obj.render.ops.warn(
            f"unresolved markers: {', '.join(resolution.unresolved_markers)}"
        )

    obj.render.ops.syntax_panel(
        resolution.rendered_prompt,
        "markdown",
        title=f"Resolved prompt \u2014 {agent_id}",
        border="cyan",
    )

    if resolution.snapshot:
        snap_table = Table(header_style="bold magenta", padding=(0, 1))
        snap_table.add_column("Marker")
        snap_table.add_column("Resource ID", style="dim")
        snap_table.add_column("Mode")
        snap_table.add_column("Version", style="dim")
        for rb in resolution.snapshot:
            snap_table.add_row(rb.marker, rb.resource_id, rb.mode, rb.version_id)
        obj.render.ops.panel(snap_table, title="Binding snapshot", border="green")
