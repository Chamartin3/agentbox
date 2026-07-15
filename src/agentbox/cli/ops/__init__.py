"""Operational CLI commands: serve, shell, cfg, resources.

Credentials moved to the ``engine`` branch (``engine cred``).
Interactive launch moved to ``agentbox run`` (use ``agentbox run --backend <backend>``
or ``agentbox run <agent>`` instead of the former ``ops launch``).
"""

from __future__ import annotations

import typer

from agentbox.cli.ops.cfg import cfg_app as _cfg_app
from agentbox.cli.ops.resource import app as _resource_app
from agentbox.cli.ops.serve import serve
from agentbox.cli.ops.shell import shell_cmd
from agentbox.cli.ops.workenv import workenv_app as _workenv_app
from agentbox.cli.shared import group_callback

app = typer.Typer(
    name="ops",
    help="Operational commands: serve, shell, cfg, resources.",
    no_args_is_help=True,
)
app.callback()(group_callback)

app.command(name="serve")(serve)
app.command(name="shell")(shell_cmd)
app.add_typer(_cfg_app, name="cfg")
_cfg_app.callback()(group_callback)
app.add_typer(_resource_app, name="resource")
app.add_typer(_workenv_app, name="workenv")
_workenv_app.callback()(group_callback)

__all__ = ["app"]
