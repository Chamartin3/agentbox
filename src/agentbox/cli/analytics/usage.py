"""Usage analytics CLI — aggregated token/cost totals."""

from __future__ import annotations

import json as _json

import typer
from rich.json import JSON

from agentbox.api.deps import get_store
from agentbox.cli._common import console

app = typer.Typer(
    name="usage",
    help="Aggregate token/cost rollups across runs.",
    no_args_is_help=True,
)


@app.command("show")
def usage_show() -> None:
    """Print the aggregate usage rollup as JSON."""
    data = get_store().aggregate_usage()
    console.print(JSON(_json.dumps(data, indent=2, default=str)))
