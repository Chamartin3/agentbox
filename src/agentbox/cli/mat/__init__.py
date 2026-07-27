"""agentbox mat — export and import CLI commands."""

from __future__ import annotations

import typer

from agentbox.cli.shared import group_callback
from agentbox.cli.mat.export_ import app as export_app
from agentbox.cli.mat.import_ import app as import_app

app = typer.Typer(
    name="mat",
    help="Materialize agents/environments to disk, and import from disk.",
    no_args_is_help=True,
)
app.callback()(group_callback)

app.add_typer(export_app, name="export", help="Write agents/environments to disk.")
export_app.callback()(group_callback)

app.add_typer(import_app, name="import", help="Load agents/skills from disk into the DB.")
import_app.callback()(group_callback)
