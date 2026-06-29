"""CLI sub-app: agentbox prompt-bindings — manage agent prompt resource bindings."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
from agentbox.cli.shared.deps import get_resource_service
# TODO(cli-arch): ResourceService (plan 090)
from agentbox.core.service import (
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
    obj: CLIContext = ctx.obj
    svc = get_resource_service()
    rows = svc.list_prompt_resources(agent_id).get("items", [])
    if not rows:
        obj.render.ops.warn(f"No prompt bindings for agent {agent_id!r}.")
        return

    obj.render.ops.bindings_table(agent_id, rows)


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
    obj: CLIContext = ctx.obj
    if len(reason.strip()) < 3:
        obj.render.ops.error("--reason must be at least 3 characters")
        raise typer.Exit(1)

    svc = get_resource_service()
    resource = svc.get_by_slug(resource_slug)
    if not resource:
        obj.render.ops.error(f"Resource not found: {resource_slug!r}")
        raise typer.Exit(2)

    existing = svc.list_prompt_resources(agent_id).get("items", [])
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

    svc.replace_prompt_resources(agent_id, kept, reason=reason)
    obj.render.ops.success(
        f"binding set: agent={agent_id} marker={marker} → {resource_slug} (mode={mode})"
    )


@prompt_bindings_app.command("preview")
def pb_preview(ctx: typer.Context, agent_id: str) -> None:
    """Preview the resolved prompt for an agent with all bindings applied."""
    obj: CLIContext = ctx.obj
    store = obj.store
    active = get_active_agent_version(store, agent_id)
    if not active:
        obj.render.ops.error(f"No active version for agent {agent_id!r}")
        raise typer.Exit(2)

    prompt_content = active.get("prompt_content") or ""
    if not prompt_content:
        obj.render.ops.warn(f"Agent {agent_id!r} has no prompt content.")
        return

    resolved_bindings = resolve_agent_prompt_bindings(store, agent_id)
    resolution = resolve_prompt(prompt_content, resolved_bindings)

    # Decompose resolution object for the renderer
    snapshot_rows: list[tuple[str, str, str, str]] | None = None
    if resolution.snapshot:
        snapshot_rows = [
            (rb.marker, rb.resource_id, rb.mode, rb.version_id)
            for rb in resolution.snapshot
        ]

    obj.render.ops.prompt_preview(
        agent_id,
        resolution.rendered_prompt,
        list(resolution.warnings),
        list(resolution.unresolved_markers),
        snapshot_rows,
    )
