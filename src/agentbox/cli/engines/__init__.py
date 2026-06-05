"""Runner-related CLI commands: profiles, providers, backends."""

from __future__ import annotations

import typer

from agentbox.cli.engines.backends import app as _backends_app
from agentbox.cli.engines.profiles import app as _profiles_app
from agentbox.cli.engines.providers import app as _providers_app

app = typer.Typer(
    name="runners",
    help="Runner profiles, providers, and backend adapters.",
    no_args_is_help=True,
)
app.add_typer(_profiles_app, name="profiles")
app.add_typer(_providers_app, name="providers")
app.add_typer(_backends_app, name="backends")

__all__ = ["app"]
