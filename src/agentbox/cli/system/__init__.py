"""System CLI commands: env-doc, host env, MCP, health, settings, tokens, project."""

from __future__ import annotations

import typer

from agentbox.cli.system.env import env_doc_app as _env_app
from agentbox.cli.system.health import health_app
from agentbox.cli.system.host import host_env_app as _host_app
from agentbox.cli.system.mcp import mcp_app as _mcp_app
from agentbox.cli.system.project import project_app
from agentbox.cli.system.settings import settings_app
from agentbox.cli.system.tokens import tokens_app

app = typer.Typer(
    name="system",
    help="System-scoped commands: env-doc, host env grants, MCP discovery.",
    no_args_is_help=True,
)
app.add_typer(_env_app, name="env")
app.add_typer(health_app, name="health")
app.add_typer(_host_app, name="host")
app.add_typer(_mcp_app, name="mcp")
app.add_typer(project_app, name="project")
app.add_typer(settings_app, name="settings")
app.add_typer(tokens_app, name="tokens")

__all__ = ["app"]
