"""Runner profiles and provider CLI commands.

Subcommand groups:
  runner-profile — Create, list, bind runner profiles
  runner-provider — List providers and their available models
"""

from __future__ import annotations

import asyncio
import json as _json

import typer
from rich.json import JSON
from rich.table import Table

from agentbox.api.deps import get_store
from agentbox.cli._common import console
from agentbox.core.agent.providers import list_providers
from agentbox.core.data.runner_profiles import RunnerProfileCreate

runner_profile_app = typer.Typer(
    name="runner-profile",
    help="Manage runner profiles (create, list, bind to agents).",
    no_args_is_help=True,
)

runner_provider_app = typer.Typer(
    name="runner-provider",
    help="List providers and query available models.",
    no_args_is_help=True,
)


# ============================================================================
# runner-profile subcommands
# ============================================================================


@runner_profile_app.command("ls")
def runner_profile_ls(
    backend: str | None = typer.Option(
        None, help="Filter by backend (e.g. 'claude_code', 'token')"
    ),
    provider: str | None = typer.Option(
        None, help="Filter by provider (e.g. 'openai', 'openrouter')"
    ),
    enabled: bool | None = typer.Option(None, help="Filter by enabled status"),
) -> None:
    """List runner profiles with optional filters."""
    store = get_store()
    profiles = store.list_runner_profiles(
        backend=backend, provider=provider, enabled=enabled
    )

    if not profiles:
        console.print("[yellow]No runner profiles found.[/yellow]")
        return

    table = Table(
        title="Runner Profiles",
        title_style="bold",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Backend", style="dim")
    table.add_column("Provider", style="dim")
    table.add_column("Model", style="dim")
    table.add_column("Enabled", justify="center")
    table.add_column("System Default", justify="center")

    for p in profiles:
        enabled_str = "[green]✓[/green]" if p.is_enabled else "[dim]·[/dim]"
        default_str = "[green]✓[/green]" if p.is_system_default else "[dim]·[/dim]"
        table.add_row(
            p.id,
            p.name,
            p.backend,
            p.provider or "—",
            p.model or "—",
            enabled_str,
            default_str,
        )

    console.print(table)


@runner_profile_app.command("get")
def runner_profile_get(profile_id: str) -> None:
    """Show runner profile details as JSON."""
    store = get_store()
    profile = store.get_runner_profile(profile_id)

    if not profile:
        console.print(f"[red]Profile not found:[/red] {profile_id}")
        raise typer.Exit(1)

    # Render as formatted JSON
    profile_dict = profile.model_dump()
    console.print(JSON(_json.dumps(profile_dict, indent=2)))


@runner_profile_app.command("create")
def runner_profile_create(
    id: str = typer.Option(..., help="Unique profile ID"),
    name: str = typer.Option(..., help="Human-readable name"),
    backend: str = typer.Option(
        ..., help="Backend kind (e.g. 'claude_code', 'token', 'opencode')"
    ),
    provider: str | None = typer.Option(None, help="Provider ID"),
    model: str | None = typer.Option(None, help="Model identifier"),
    base_url: str | None = typer.Option(None, help="Custom base URL"),
    api_key_env: str | None = typer.Option(
        None, help="Environment variable name for API key"
    ),
    description: str | None = typer.Option(None, help="Profile description"),
    system_default: bool = typer.Option(False, help="Set as system default profile"),
) -> None:
    """Create a new runner profile."""
    store = get_store()

    profile_data = RunnerProfileCreate(
        id=id,
        name=name,
        backend=backend,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        description=description,
        is_system_default=system_default,
    )

    profile = store.create_runner_profile(profile_data)
    console.print(f"[green]Created runner profile[/green] [bold]{profile.id}[/bold]")
    console.print(JSON(_json.dumps(profile.model_dump(), indent=2)))


@runner_profile_app.command("set-agent")
def runner_profile_set_agent(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    profile_id: str = typer.Argument(..., help="Runner profile ID"),
) -> None:
    """Bind a runner profile to an agent."""
    store = get_store()

    # Verify profile exists
    profile = store.get_runner_profile(profile_id)
    if not profile:
        console.print(f"[red]Profile not found:[/red] {profile_id}")
        raise typer.Exit(1)

    store.set_agent_runner_profile(agent_id, profile_id)
    console.print(
        f"[green]Bound agent[/green] [bold]{agent_id}[/bold] "
        f"[green]to profile[/green] [bold]{profile_id}[/bold]"
    )


@runner_profile_app.command("clear-agent")
def runner_profile_clear_agent(
    agent_id: str = typer.Argument(..., help="Agent ID"),
) -> None:
    """Remove the runner profile binding from an agent."""
    store = get_store()
    store.clear_agent_runner_profile(agent_id)
    console.print(
        f"[green]Cleared profile binding for agent[/green] [bold]{agent_id}[/bold]"
    )


@runner_profile_app.command("stats")
def runner_profile_stats(
    profile_id: str | None = typer.Argument(
        None, help="Profile ID (optional; if omitted, lists all)"
    ),
) -> None:
    """Show per-profile statistics."""
    store = get_store()

    if profile_id:
        # Single profile stats
        stats = store.runner_profile_stats(profile_id)
        table = Table(
            title=f"Stats for profile {profile_id}",
            title_style="bold",
            header_style="bold cyan",
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Runs", str(stats.runs))
        table.add_row("Succeeded", str(stats.succeeded))
        table.add_row("Failed", str(stats.failed))
        table.add_row("Input Tokens", str(stats.input_tokens))
        table.add_row("Output Tokens", str(stats.output_tokens))
        table.add_row("Cost (USD)", f"${stats.cost_usd:.4f}" if stats.cost_usd else "—")
        table.add_row(
            "Avg Duration (ms)",
            f"{stats.avg_duration_ms:.1f}" if stats.avg_duration_ms else "—",
        )
        table.add_row("Last Run", stats.last_run_at or "—")
        console.print(table)
    else:
        # List all profile stats
        all_stats = store.list_runner_profile_stats()

        if not all_stats:
            console.print("[yellow]No profile statistics found.[/yellow]")
            return

        table = Table(
            title="All Runner Profile Stats",
            title_style="bold",
            header_style="bold cyan",
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Profile ID", style="bold")
        table.add_column("Runs", justify="right")
        table.add_column("Succeeded", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Input Tokens", justify="right")
        table.add_column("Output Tokens", justify="right")
        table.add_column("Cost (USD)", justify="right")

        for stats in all_stats:
            table.add_row(
                stats.profile_id,
                str(stats.runs),
                str(stats.succeeded),
                str(stats.failed),
                str(stats.input_tokens),
                str(stats.output_tokens),
                f"${stats.cost_usd:.4f}" if stats.cost_usd else "—",
            )

        console.print(table)


@runner_profile_app.command("delete")
def runner_profile_delete(
    profile_id: str = typer.Argument(..., help="Profile ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a runner profile."""
    store = get_store()

    profile = store.get_runner_profile(profile_id)
    if not profile:
        console.print(f"[red]Profile not found:[/red] {profile_id}")
        raise typer.Exit(1)

    if not yes:
        console.print(
            f"[yellow]Delete profile[/yellow] [bold]{profile_id}[/bold]? "
            "[dim](use --yes to skip confirmation)[/dim]"
        )
        confirm = typer.confirm("Continue?", default=False)
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    store.delete_runner_profile(profile_id)
    console.print(f"[green]Deleted runner profile[/green] [bold]{profile_id}[/bold]")


# ============================================================================
# runner-provider subcommands
# ============================================================================


@runner_provider_app.command("ls")
def runner_provider_ls() -> None:
    """List available provider descriptors."""
    descriptors = list_providers()

    if not descriptors:
        console.print("[yellow]No providers found.[/yellow]")
        return

    table = Table(
        title="Providers",
        title_style="bold",
        header_style="bold cyan",
        show_lines=False,
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
            desc.id,
            desc.label,
            desc.backend,
            api_key_str,
            model_listing_str,
        )

    console.print(table)


@runner_provider_app.command("models")
def runner_provider_models(
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

    store = get_store()

    # Build effective config
    config = None
    if profile_id:
        profile = store.get_runner_profile(profile_id)
        if not profile:
            console.print(f"[red]Profile not found:[/red] {profile_id}")
            raise typer.Exit(1)

        # Create a mock config from profile
        class MockConfig:
            pass

        config = MockConfig()
        config.base_url = profile.base_url or base_url
        config.api_key_env = profile.api_key_env or api_key_env
    else:
        # Create minimal config
        class MockConfig:
            pass

        config = MockConfig()
        config.base_url = base_url
        config.api_key_env = api_key_env

    # Verify provider exists
    provider = get_provider(provider_id)
    if not provider:
        console.print(f"[red]Provider not found:[/red] {provider_id}")
        raise typer.Exit(1)

    if not provider.descriptor.supports_model_listing:
        console.print(
            f"[yellow]Provider {provider_id} does not support model listing.[/yellow]"
        )
        raise typer.Exit(1)

    # Fetch models asynchronously
    try:
        models = asyncio.run(provider.list_models(config, refresh=refresh))
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
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Context Length", justify="right", style="dim")

    for model in models:
        ctx_len = getattr(model, "context_length", None)
        ctx_len_str = str(ctx_len) if ctx_len else "—"
        table.add_row(
            model.id,
            model.name,
            ctx_len_str,
        )

    console.print(table)


@runner_provider_app.command("refresh")
def runner_provider_refresh() -> None:
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
