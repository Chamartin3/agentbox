"""Agent prompt CLI command."""

from __future__ import annotations

import typer
from rich.syntax import Syntax

from agentbox.cli._common import console, resolve_agent
from agentbox.cli._deps import get_settings, get_store
from agentbox.cli.agents.crud import agent_app
from agentbox.core import prompts
from agentbox.core.service import get_prompt_version


@agent_app.command("prompt")
def agent_prompt(
    agent_id: str,
    version: int | None = typer.Option(
        None, "--version", help="Prompt version to display"
    ),
) -> None:
    """Print the agent's system prompt."""
    a = resolve_agent(agent_id)
    settings = get_settings()
    store = get_store()

    if version is not None:
        committed = get_prompt_version(store, agent_id, version)
        if committed is None:
            console.print(
                f"[red]version {version} not found for agent {agent_id!r}[/red]"
            )
            raise typer.Exit(2)
        content = committed["content"]
    else:
        doc = prompts.read_versioned(a, settings.project_root, store)
        content = doc.content

    if not content:
        console.print("[yellow]No prompt content for this agent.[/yellow]")
        return

    console.print(Syntax(content, "markdown", theme="ansi_dark"))
