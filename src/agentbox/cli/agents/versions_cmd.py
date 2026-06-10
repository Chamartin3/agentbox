"""Agent version lifecycle CLI commands (draft, publish, rollback)."""

from __future__ import annotations

import typer

from agentbox.cli._common import console, handle_cli_errors, resolve_agent
from agentbox.cli._deps import get_store
from agentbox.cli.agents.crud import agent_app
from agentbox.core.service import (
    branch_agent_draft,
    publish_agent_version,
    rollback_agent_to,
)


@agent_app.command("draft")
def agent_draft(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Create a new draft version by cloning the active version."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = branch_agent_draft(store, agent_id, author=author)
    console.print(
        f"[green]draft created[/green] v{result.get('version')} "
        f"(id={result.get('id')})"
    )


@agent_app.command("publish")
def agent_publish(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Version number to publish"),
    reason: str = typer.Option("cli publish", "--reason", help="Publish reason"),
) -> None:
    """Publish a draft version (set as active)."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = publish_agent_version(store, agent_id, version, reason)
    console.print(
        f"[green]published[/green] v{result.get('version')} "
        f"(id={result.get('id')})"
    )


@agent_app.command("rollback")
def agent_rollback(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    version: int = typer.Argument(..., help="Target version to roll back to"),
    reason: str = typer.Option(..., "--reason", help="Rollback reason (min 3 chars)"),
    author: str = typer.Option("cli", "--author", help="Author identifier"),
) -> None:
    """Roll back to a previous agent version (creates a new version)."""
    resolve_agent(agent_id)
    store = get_store()
    with handle_cli_errors():
        result = rollback_agent_to(store, agent_id, version, reason, author=author)
    console.print(
        f"[green]rolled back[/green] to v{version} (new v{result.get('version')})"
    )
