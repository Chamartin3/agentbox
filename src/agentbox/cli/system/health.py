"""system health — server health check."""

from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

import typer

from agentbox.cli.shared import CliCtx

health_app = typer.Typer(
    name="health",
    help="Check server health.",
    no_args_is_help=True,
)


@health_app.command("check")
def health_check(
    ctx: typer.Context,
    base_url: str = typer.Option(
        "http://localhost:8765", "--url", help="Server base URL"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON response"
    ),
) -> None:
    """Check the server health endpoint.

    If the server is not running, exit with code 2.
    """
    obj: CliCtx = ctx.obj

    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except URLError:
        obj.render.system.health_unreachable()
        raise typer.Exit(2)
    except Exception as exc:
        obj.render.system.health_error(str(exc))
        raise typer.Exit(1)

    if json_output:
        obj.render.system.health_status_json(data)
    else:
        obj.render.system.health_status_view(data)
