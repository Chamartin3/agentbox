"""Agent CLI commands."""

from __future__ import annotations

from agentbox.cli.agents.crud import agent_app as app
from agentbox.cli.agents.grants import grants_app
from agentbox.cli.agents.prompts import prompts_app
from agentbox.cli.agents.tools import tools_app
from agentbox.cli.agents.validation import validation_app
from agentbox.cli.agents.versions import versions_app

app.add_typer(grants_app, name="grants")
app.add_typer(prompts_app, name="prompts")
app.add_typer(tools_app, name="tools")
app.add_typer(validation_app, name="validation")
app.add_typer(versions_app, name="versions")

__all__ = ["app"]
