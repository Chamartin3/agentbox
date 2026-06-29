"""Resource CLI commands: repo and bindings."""

from __future__ import annotations

import typer

from agentbox.cli.ops.resource.bind import prompt_bindings_app as _bindings_app
from agentbox.cli.ops.resource.repo import repo_app
from agentbox.cli.shared import group_callback

app = typer.Typer(
    name="resource",
    help="Repo resources and prompt resource bindings.",
    no_args_is_help=True,
)
app.callback()(group_callback)

app.add_typer(repo_app, name="repo")
repo_app.callback()(group_callback)
app.add_typer(_bindings_app, name="bind")
_bindings_app.callback()(group_callback)

__all__ = ["app"]
