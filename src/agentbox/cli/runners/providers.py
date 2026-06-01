"""Runner provider CLI commands — list providers and query models."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import typer
from rich.table import Table

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.core.agent.providers import list_providers
from agentbox.core.service import get_runner_profile

app = typer.Typer(
    name="providers",
    help="List providers and query available models.",
    no_args_is_help=True,
)


@app.command("ls")
def provider_ls() -> None:
    """List available provider descriptors."""
    descriptors = list_providers()

    if not descriptors:
        console.print("[yellow]No providers found.[/yellow]")
        return

    table = Table(
        title="Providers",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Label", style="cyan")
    table.add_column("Backend", style="dim")
    table.add_column("Requires API Key", justify="center")
    table.add_column("Supports Model Listing", justify="center")

    for desc in descriptors:
        api_key_str = "[green]✓[/green]" if desc.requires_api_key else "[dim]·[/dim]"
        model_listing_str = (
            "[green]✓[/green]" if desc.supports_model_listing else "[dim]·[/dim]"
        )
        table.add_row(
            desc.id, desc.label, desc.backend, api_key_str, model_listing_str
        )

    console.print(table)


@app.command("models")
def provider_models(
    provider_id: str = typer.Argument(..., help="Provider ID (e.g. 'openai')"),
    profile_id: str | None = typer.Option(
        None, help="Use config from a runner profile"
    ),
    base_url: str | None = typer.Option(
        None, help="Override base URL (for custom endpoints)"
    ),
    api_key_env: str | None = typer.Option(None, help="Override API key env var name"),
    refresh: bool = typer.Option(False, help="Bypass cache and fetch fresh models"),
) -> None:
    """List available models for a provider."""
    from agentbox.core.agent.providers import get_provider
    from agentbox.core.agent.providers.registry import list_models as registry_list_models

    store = get_store()

    if profile_id:
        profile = get_runner_profile(store, profile_id)
        if not profile:
            console.print(f"[red]Profile not found:[/red] {profile_id}")
            raise typer.Exit(1)
        config = SimpleNamespace(
            base_url=profile.base_url or base_url,
            api_key_env=profile.api_key_env or api_key_env,
            backend=None,
        )
    else:
        config = SimpleNamespace(
            base_url=base_url,
            api_key_env=api_key_env,
            backend=None,
        )

    provider = get_provider(provider_id)
    if not provider:
        console.print(f"[red]Provider not found:[/red] {provider_id}")
        raise typer.Exit(1)

    if not provider.descriptor.supports_model_listing:
        console.print(
            f"[yellow]Provider {provider_id} does not support model listing.[/yellow]"
        )
        raise typer.Exit(1)

    try:
        models = asyncio.run(
            registry_list_models(provider_id, config, refresh=refresh)
        )
    except Exception as e:
        console.print(f"[red]Error fetching models:[/red] {e}")
        raise typer.Exit(1)  # noqa: B904

    if not models:
        console.print(f"[yellow]No models found for provider {provider_id}.[/yellow]")
        return

    table = Table(
        title=f"Models for {provider_id}",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Context Length", justify="right", style="dim")

    for model in models:
        ctx_len = getattr(model, "context_length", None)
        ctx_len_str = str(ctx_len) if ctx_len else "—"
        table.add_row(model.id, model.name, ctx_len_str)

    console.print(table)


@app.command("refresh")
def provider_refresh() -> None:
    """Re-discover dynamic providers (currently: opencode CLI)."""
    from agentbox.core.agent.providers.registry import refresh_opencode_providers

    discovered = refresh_opencode_providers()
    if not discovered:
        console.print(
            "[yellow]No opencode providers discovered "
            "(binary missing or call failed).[/yellow]"
        )
        return
    console.print(
        f"[green]Discovered {len(discovered)} opencode provider(s):[/green] "
        + ", ".join(discovered)
    )
