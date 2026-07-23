"""agentbox CLI — 8-branch tree.

Top-level branches: agent | work | engine | system | ops | history | mat.
Top-level commands: run.

Entry point: ``agentbox.cli:app`` (wired in pyproject.toml).
"""

from __future__ import annotations

import typer

from agentbox.cli.agent import app as agent_app
from agentbox.cli.engine import app as engine_app
from agentbox.cli.history import app as history_app
from agentbox.cli.mat import app as mat_app
from agentbox.cli.ops import app as ops_app
from agentbox.cli.run import run_cmd
from agentbox.cli.system import app as system_app
from agentbox.cli.work import app as work_app

app = typer.Typer(
    name="agentbox",
    help=(
        "Agent orchestration — "
        "branches: agent | work | engine | system | ops | history | mat  "
        "commands: run"
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
)

app.add_typer(agent_app, name="agent")
app.command("run")(run_cmd)
app.add_typer(work_app, name="work")
app.add_typer(engine_app, name="engine")
app.add_typer(system_app, name="system")
app.add_typer(ops_app, name="ops")
app.add_typer(history_app, name="history")
app.add_typer(mat_app, name="mat")

__all__ = ["app"]
