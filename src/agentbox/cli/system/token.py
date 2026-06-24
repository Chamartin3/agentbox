"""system tokens — manage API tokens."""

from __future__ import annotations

import secrets

import typer
from rich.table import Table

from agentbox.cli.shared import console, get_store
from agentbox.core.service import (
    SystemService,
    delete_api_token,  # noqa: F401
    rotate_api_token,  # noqa: F401
)

token_app = typer.Typer(
    name="token",
    help="Manage API tokens.",
    no_args_is_help=True,
)


@token_app.command("ls")
def tokens_ls(
    environment: str | None = typer.Option(
        None, "--env", help="Filter by environment"
    ),
) -> None:
    """List API tokens."""
    store = get_store()
    items = SystemService().list_api_tokens(environment=environment)
    if not items:
        console.print("[dim]no tokens[/dim]")
        return

    table = Table(title="API Tokens", header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Environment")
    table.add_column("Created")
    for t in items:
        env = t.get("environment", "")
        table.add_row(
            t["id"][:12],
            t.get("name", ""),
            env,
            t.get("created_at", ""),
        )
    console.print(table)


@token_app.command("new")
def tokens_create(
    name: str = typer.Argument(..., help="Token name"),
    environment: str = typer.Option(
        "production", "--env", help="Token environment"
    ),
) -> None:
    """Create a new API token. Prints the secret once; store it securely."""
    secret = secrets.token_urlsafe(32)
    store = get_store()
    result = SystemService().create_api_token(name=name, environment=environment)
    console.print(
        f"[green]created[/green] token {result['id']!r} for environment {environment!r}"
    )
    console.print(f"[bold yellow]secret (save this):[/bold yellow] {secret}")


@token_app.command("rotate")
def tokens_rotate(
    token_id: str = typer.Argument(..., help="Token ID"),
) -> None:
    """Rotate a token's secret. Prints the new secret once."""
    secret = secrets.token_urlsafe(32)
    store = get_store()
    result = SystemService().rotate_api_token(token_id, secret=secret)
    if result is None:
        console.print(f"[red]token {token_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[green]rotated[/green] token {token_id!r}")
    console.print(f"[bold yellow]new secret (save this):[/bold yellow] {secret}")


@token_app.command("rm")
def tokens_rm(
    token_id: str = typer.Argument(..., help="Token ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an API token. This action is irreversible."""
    if not yes:
        confirm = typer.confirm(f"Delete token {token_id!r}? This is irreversible.")
        if not confirm:
            raise typer.Exit(0)
    store = get_store()
    result = SystemService().delete_api_token(token_id)
    if not result:
        console.print(f"[red]token {token_id!r} not found[/red]")
        raise typer.Exit(1)
    console.print(f"[yellow]deleted[/yellow] token {token_id!r}")
