"""agents validation — read/write per-agent inline validators."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from agentbox.cli._deps import get_settings, get_store
from agentbox.cli._common import console, resolve_agent
from agentbox.core.service.agents import (
    AgentServiceError,
    get_agent_validation,
    put_agent_validation,
)

validation_app = typer.Typer(
    name="validation",
    help="Read/write per-agent inline validators.",
    no_args_is_help=True,
)


@validation_app.command("get")
def validation_get(
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """Show validation config for an agent (input + output directions)."""
    resolve_agent(agent_id)
    store = get_store()
    result = get_agent_validation(store, agent_id)

    for direction in ("input", "output"):
        section = result.get(direction) or {}
        validators = section.get("validators", [])
        if validators:
            console.print(
                Panel(
                    Syntax(
                        json.dumps(validators, indent=2),
                        "json",
                        theme="ansi_dark",
                    ),
                    title=f"[bold]{direction}[/bold] validators",
                )
            )
        else:
            console.print(f"[dim]{direction}: no validators[/dim]")


@validation_app.command("put")
def validation_put(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    direction: str = typer.Argument(..., help="Direction: input or output"),
    validators_json: str = typer.Argument(..., help="JSON array of validators"),
    reason: str = typer.Option("cli edit", "--reason", help="Edit reason"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Set inline validators for a direction.

    Example: agents validation put my-agent output '[{"kind":"http","endpoint":"https://..."}]'
    """
    if direction not in ("input", "output"):
        console.print("[red]direction must be 'input' or 'output'[/red]")
        raise typer.Exit(2)

    resolve_agent(agent_id)

    try:
        validators = json.loads(validators_json)
    except json.JSONDecodeError as exc:
        console.print(f"[red]invalid JSON: {exc}[/red]")
        raise typer.Exit(2)

    input_validators = validators if direction == "input" else None
    output_validators = validators if direction == "output" else None

    try:
        result = put_agent_validation(
            store=get_store(),
            settings=get_settings(),
            agent_id=agent_id,
            input_validators=input_validators,
            output_validators=output_validators,
            reason=reason,
            actor=actor,
        )
    except AgentServiceError as exc:
        console.print(f"[red]{exc.code}: {exc.detail}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]updated[/green] {direction} validators — v{result.get('version', '?')}")
