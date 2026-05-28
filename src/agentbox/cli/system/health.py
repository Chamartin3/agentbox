"""system health — server health check."""

from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

import typer

from agentbox.cli._common import console

health_app = typer.Typer(
    name="health",
    help="Check server health.",
    no_args_is_help=True,
)


@health_app.command("check")
def health_check(
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
    try:
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except URLError:
        console.print("[red]server is not reachable[/red]")
        raise typer.Exit(2)
    except Exception as exc:
        console.print(f"[red]health check failed: {exc}[/red]")
        raise typer.Exit(1)

    if json_output:
        console.print(json.dumps(data, indent=2, default=str))
    else:
        status = data.get("status", "unknown")
        color = "green" if status == "ok" else "red"
        console.print(f"health: [{color}]{status}[/{color}]")
        if "version" in data:
            console.print(f"version: {data['version']}")
        if "db" in data:
            console.print(f"db: {data['db']}")
        if "uptime" in data:
            console.print(f"uptime: {data['uptime']}")
