"""Agent check — get/set inline validators per agent."""

from __future__ import annotations

import json

import typer

from agentbox.cli.shared import CLIContext, resolve_agent
from agentbox.core.service.agents import AgentServiceError

check_app = typer.Typer(
    name="check",
    help="Get or set per-agent inline validators.",
    no_args_is_help=True,
)


@check_app.command("get")
def check_get(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """Show validation config for an agent (input + output directions)."""
    obj: CLIContext = ctx.obj
    resolve_agent(agent_id)
    result = obj.agents.get_agent_validation(agent_id)
    obj.render.agent.validation_report(result)


@check_app.command("set")
def check_set(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    direction: str = typer.Argument(..., help="Direction: input or output"),
    validators_json: str = typer.Argument(..., help="JSON array of validators"),
    reason: str = typer.Option("cli edit", "--reason", help="Edit reason"),
    actor: str | None = typer.Option(None, "--actor", help="Actor identifier"),
) -> None:
    """Set inline validators for a direction.

    Example: agent check set my-agent output '[{"kind":"http","endpoint":"https://..."}]'
    """
    obj: CLIContext = ctx.obj

    if direction not in ("input", "output"):
        obj.render.agent.error("direction must be 'input' or 'output'")
        raise typer.Exit(2)

    resolve_agent(agent_id)

    try:
        validators = json.loads(validators_json)
    except json.JSONDecodeError as exc:
        obj.render.agent.error(f"invalid JSON: {exc}")
        raise typer.Exit(2)

    input_validators = validators if direction == "input" else None
    output_validators = validators if direction == "output" else None

    try:
        result = obj.agents.put_agent_validation(
            agent_id=agent_id,
            input_validators=input_validators,
            output_validators=output_validators,
            reason=reason,
            actor=actor,
            settings=obj.settings,
        )
    except AgentServiceError as exc:
        obj.render.agent.error(f"{exc.code}: {exc.detail}")
        raise typer.Exit(1)

    obj.render.agent.validation_updated(direction, result.get("agent_version_id", "?"))