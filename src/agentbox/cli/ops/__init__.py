"""Operational CLI commands: launch, shell, cfg, migrate."""

from __future__ import annotations

import typer

from agentbox.cli.engines.credentials import creds_app as _creds_app
from agentbox.cli.ops.cfg import cfg_app as _cfg_app
from agentbox.cli.ops.launch import launch_cmd
from agentbox.cli.ops.migrate import migrate_app as _migrate_app
from agentbox.cli.ops.shell import shell_cmd
from agentbox.cli.ops.workenv import workenv_app as _workenv_app

app = typer.Typer(
    name="ops",
    help="Operational commands: launch, shell, cfg, creds, migrate, workenv.",
    no_args_is_help=True,
)
app.add_typer(_cfg_app, name="cfg")
app.add_typer(_creds_app, name="creds")
app.add_typer(_migrate_app, name="migrate")
app.command(name="launch")(launch_cmd)
app.command(name="shell")(shell_cmd)
app.add_typer(_workenv_app, name="workenv")

__all__ = ["app"]
