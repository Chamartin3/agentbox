"""System CLI commands: doctor, env-doc, host env, MCP, health, settings, tokens, project."""

from __future__ import annotations

import typer

from agentbox.cli.shared import group_callback
from agentbox.cli.system.doctor import doctor
from agentbox.cli.system.env import env_doc_app as _env_app
from agentbox.cli.system.health import health_app
from agentbox.cli.system.host import host_env_app as _host_app
from agentbox.cli.system.mcp import mcp_app as _mcp_app
from agentbox.cli.system.project import project_app
from agentbox.cli.system.settings import settings_app
from agentbox.cli.system.tokens import tokens_app

app = typer.Typer(
    name="system",
    help="System-scoped commands: doctor, env-doc, host env grants, MCP discovery.",
    no_args_is_help=True,
)
app.callback()(group_callback)

app.command("doctor")(doctor)
app.add_typer(_env_app, name="env")
_env_app.callback()(group_callback)

app.add_typer(health_app, name="health")
health_app.callback()(group_callback)

app.add_typer(_host_app, name="host")
_host_app.callback()(group_callback)

app.add_typer(_mcp_app, name="mcp")
_mcp_app.callback()(group_callback)

app.add_typer(project_app, name="project")
project_app.callback()(group_callback)

app.add_typer(settings_app, name="settings")
settings_app.callback()(group_callback)

app.add_typer(tokens_app, name="tokens")
tokens_app.callback()(group_callback)

__all__ = ["app"]
