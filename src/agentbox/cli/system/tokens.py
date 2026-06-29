"""system tokens — manage API tokens."""

from __future__ import annotations

import secrets

import typer

from agentbox.cli.shared import CLIContext

tokens_app = typer.Typer(
    name="tokens",
    help="Manage API tokens.",
    no_args_is_help=True,
)


@tokens_app.command("ls")
def tokens_ls(
    ctx: typer.Context,
    environment: str | None = typer.Option(
        None, "--env", help="Filter by environment"
    ),
) -> None:
    """List API tokens."""
    obj: CLIContext = ctx.obj
    items = obj.system.list_api_tokens(environment=environment)
    obj.render.system.tokens_table(items)


@tokens_app.command("create")
def tokens_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Token name"),
    environment: str = typer.Option(
        "production", "--env", help="Token environment"
    ),
) -> None:
    """Create a new API token. Prints the secret once; store it securely."""
    obj: CLIContext = ctx.obj
    secret = secrets.token_urlsafe(32)
    result = obj.system.create_api_token(
        name=name, environment=environment, secret=secret
    )
    obj.render.system.token_created(result["id"], environment, secret)


@tokens_app.command("rotate")
def tokens_rotate(
    ctx: typer.Context,
    token_id: str = typer.Argument(..., help="Token ID"),
) -> None:
    """Rotate a token's secret. Prints the new secret once."""
    obj: CLIContext = ctx.obj
    secret = secrets.token_urlsafe(32)
    result = obj.system.rotate_api_token(token_id, secret=secret)
    if result is None:
        obj.render.system.token_not_found(token_id)
        raise typer.Exit(1)
    obj.render.system.token_rotated(token_id, secret)


@tokens_app.command("rm")
def tokens_rm(
    ctx: typer.Context,
    token_id: str = typer.Argument(..., help="Token ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an API token. This action is irreversible."""
    obj: CLIContext = ctx.obj
    if not yes:
        confirm = typer.confirm(f"Delete token {token_id!r}? This is irreversible.")
        if not confirm:
            raise typer.Exit(0)
    result = obj.system.delete_api_token(token_id)
    if not result:
        obj.render.system.token_not_found(token_id)
        raise typer.Exit(1)
    obj.render.system.token_deleted(token_id)
