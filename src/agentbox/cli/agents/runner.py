"""Agent runner profile CLI command."""

from __future__ import annotations

import typer

from agentbox.cli._common import console, resolve_agent
from agentbox.cli._deps import get_store
from agentbox.cli.agents.crud import agent_app
from agentbox.core.service import (
    clear_agent_runner_profile,
    get_agent_runner_profile,
    get_runner_profile,
    set_agent_runner_profile,
)


@agent_app.command("runner-profile")
def agent_runner_profile(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    get: bool = typer.Option(False, "--get", help="Show the bound runner profile"),
    set_: str | None = typer.Option(
        None, "--set", help="Runner profile ID to bind"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Remove the runner profile binding"
    ),
) -> None:
    """Get, set, or clear the runner profile bound to an agent.

    Examples:
        agents runner-profile my-agent --get
        agents runner-profile my-agent --set <profile_id>
        agents runner-profile my-agent --clear
    """
    if sum([get, set_ is not None, clear]) != 1:
        console.print(
            "[red]exactly one of --get, --set, or --clear must be specified[/red]"
        )
        raise typer.Exit(2)

    resolve_agent(agent_id)
    store = get_store()

    if get:
        profile = get_agent_runner_profile(store, agent_id)
        if profile is None:
            console.print("[dim]no runner profile bound[/dim]")
        else:
            console.print(
                f"[bold]{profile.id}[/bold] — {profile.name} "
                f"([cyan]{profile.backend}[/cyan] / {profile.provider or 'default'})"
            )
    elif set_:
        profile = get_runner_profile(store, set_)
        if profile is None:
            console.print(f"[red]runner profile {set_!r} not found[/red]")
            raise typer.Exit(1)
        set_agent_runner_profile(store, agent_id, set_)
        console.print(f"[green]bound[/green] profile {set_!r} to {agent_id!r}")
    elif clear:
        clear_agent_runner_profile(store, agent_id)
        console.print(f"[yellow]cleared[/yellow] profile binding for {agent_id!r}")
