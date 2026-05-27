"""Resource CLI commands: repo resources and prompt bindings."""

from __future__ import annotations

import typer

from agentbox.cli.resources.bindings import prompt_bindings_app as _bindings_app
from agentbox.cli.resources.repo import resource_app as _repo_app

app = typer.Typer(
    name="resources",
    help="Repo resources and prompt resource bindings.",
    no_args_is_help=True,
)
app.add_typer(_repo_app, name="repo")
app.add_typer(_bindings_app, name="bindings")

__all__ = ["app"]
