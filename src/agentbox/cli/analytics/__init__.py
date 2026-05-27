"""Analytics CLI commands: activity, usage."""

from __future__ import annotations

import typer

from agentbox.cli.analytics.activity import app as _activity_app
from agentbox.cli.analytics.usage import app as _usage_app

app = typer.Typer(
    name="analytics",
    help="Activity and usage analytics.",
    no_args_is_help=True,
)
app.add_typer(_activity_app, name="activity")
app.add_typer(_usage_app, name="usage")

__all__ = ["app"]
