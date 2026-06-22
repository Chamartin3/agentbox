"""Resource CLI commands: repo and bindings."""

from __future__ import annotations

import typer

from agentbox.cli.ops.resource.bind import prompt_bindings_app as _bindings_app
from agentbox.cli.ops.resource.repo import repo_app

app = typer.Typer(
    name="resource",
    help="Repo resources and prompt resource bindings.",
    no_args_is_help=True,
)
app.add_typer(repo_app, name="repo")
app.add_typer(_bindings_app, name="bind")

__all__ = ["app"]
