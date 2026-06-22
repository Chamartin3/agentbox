"""Engine branch — runner profiles, providers, backends, and credentials."""

from __future__ import annotations

import typer


from agentbox.cli.engine.backend import app as _backends_app
from agentbox.cli.engine.cred import creds_app as _creds_app
from agentbox.cli.engine.profile import app as _profiles_app
from agentbox.cli.engine.provider import app as _providers_app

app = typer.Typer(
    name="engine",
    help="Runner profiles, providers, backends, and credentials.",
    no_args_is_help=True
)
app.add_typer(_profiles_app, name="profile")
app.add_typer(_providers_app, name="provider")
app.add_typer(_backends_app, name="backend")
app.add_typer(_creds_app, name="cred")

__all__ = ["app"]
