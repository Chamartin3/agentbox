"""Operational CLI commands: serve, shell, cfg, migrate, resources.

Credentials moved to the ``engine`` branch (``engine cred``).
Interactive launch moved to ``agentbox run`` (use ``agentbox run --backend <backend>``
or ``agentbox run <agent>`` instead of the former ``ops launch``).
"""

from __future__ import annotations

import typer

from agentbox.cli.ops.cfg import cfg_app as _cfg_app
from agentbox.cli.ops.migrate import migrate_app as _migrate_app
from agentbox.cli.ops.resource import app as _resource_app
from agentbox.cli.ops.serve import serve
from agentbox.cli.ops.shell import shell_cmd
from agentbox.cli.ops.workenv import workenv_app as _workenv_app

app = typer.Typer(
    name="ops",
    help="Operational commands: serve, shell, cfg, migrate, resources.",
    no_args_is_help=True,
)
app.command(name="serve")(serve)
app.command(name="shell")(shell_cmd)
app.add_typer(_cfg_app, name="cfg")
app.add_typer(_migrate_app, name="migrate")
app.add_typer(_resource_app, name="resource")
# ponytail: workenv still a separate group; fold into `cfg` in a later cleanup.
app.add_typer(_workenv_app, name="workenv")

__all__ = ["app"]
