"""Runner profile CLI commands — create, list, bind, stats, delete."""

from __future__ import annotations

import json as _json

import typer
from rich.json import JSON
from rich.table import Table

from agentbox.cli.shared import console, get_store
from agentbox.core.service import (
    list_runner_profiles,
    get_runner_profile,
    create_runner_profile,
    bind_runner_profile,
    runner_profile_stats,
    list_runner_profile_stats,
    delete_runner_profile,
    RunnerProfileCreate,
)

app = typer.Typer(
    name="profiles",
    help="Manage runner profiles (create, list, bind to agents).",
    no_args_is_help=True,
)


@app.command("ls")
def profile_ls(
    backend: str | None = typer.Option(
        None, help="Filter by backend (e.g. 'claude_code', 'token')"
    ),
    provider: str | None = typer.Option(
        None, help="Filter by provider (e.g. 'openai', 'openrouter')"
    ),
    enabled: bool | None = typer.Option(None, help="Filter by enabled status"),
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List runner profiles with optional filters."""
    store = get_store()
    profiles = list_runner_profiles(
        store, backend=backend, provider=provider, enabled=enabled
    )

    if json_output:
        console.print(
            _json.dumps([p.model_dump() for p in profiles], indent=2)
        )
        return

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


@app.command("show")
def profile_get(profile_id: str) -> None:
    """Show runner profile details as JSON."""
    store = get_store()
    profile = get_runner_profile(store, profile_id)

    if not profile:
        console.print(f"[red]Profile not found:[/red] {profile_id}")
        raise typer.Exit(1)

    console.print(JSON(_json.dumps(profile.model_dump(), indent=2)))


@app.command("new")
def profile_create(
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
    profile = create_runner_profile(
        store,
        RunnerProfileCreate(
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
    )
    console.print(f"[green]Created runner profile[/green] [bold]{profile.id}[/bold]")
    console.print(JSON(_json.dumps(profile.model_dump(), indent=2)))


@app.command("bind")
def profile_bind(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    profile_id: str = typer.Argument(
        None, help="Runner profile ID (omit with --clear to unbind)"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Remove the profile binding from the agent"
    ),
) -> None:
    """Bind a runner profile to an agent, or clear it with --clear."""
    store = get_store()
    if clear:
        get_store().clear_agent_runner_profile(agent_id)
        console.print(
            f"[green]Cleared profile binding for agent[/green] [bold]{agent_id}[/bold]"
        )
        return
    if not profile_id:
        console.print("[red]Either provide a profile_id or use --clear[/red]")
        raise typer.Exit(2)
    if not get_runner_profile(store, profile_id):
        console.print(f"[red]Profile not found:[/red] {profile_id}")
        raise typer.Exit(1)
    bind_runner_profile(store, agent_id, profile_id)
    console.print(
        f"[green]Bound agent[/green] [bold]{agent_id}[/bold] "
        f"[green]to profile[/green] [bold]{profile_id}[/bold]"
    )


@app.command("stats")
def profile_stats(
    profile_id: str | None = typer.Argument(
        None, help="Profile ID (optional; if omitted, lists all)"
    ),
) -> None:
    """Show per-profile statistics."""
    store = get_store()

    if profile_id:
        stats = runner_profile_stats(store, profile_id)
        table = Table(
            title=f"Stats for profile {profile_id}",
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Runs", str(stats.runs))
        table.add_row("Succeeded", str(stats.succeeded))
        table.add_row("Failed", str(stats.failed))
        table.add_row("Input Tokens", str(stats.input_tokens))
        table.add_row("Output Tokens", str(stats.output_tokens))
        table.add_row(
            "Cost (USD)", f"${stats.cost_usd:.4f}" if stats.cost_usd else "—"
        )
        table.add_row(
            "Avg Duration (ms)",
            f"{stats.avg_duration_ms:.1f}" if stats.avg_duration_ms else "—",
        )
        table.add_row("Last Run", stats.last_run_at or "—")
        console.print(table)
        return

    all_stats = list_runner_profile_stats(store)
    if not all_stats:
        console.print("[yellow]No profile statistics found.[/yellow]")
        return

    table = Table(
        title="All Runner Profile Stats",
        title_style="bold",
        header_style="bold cyan",
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


@app.command("rm")
def profile_delete(
    profile_id: str = typer.Argument(..., help="Profile ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a runner profile."""
    store = get_store()
    if not get_runner_profile(store, profile_id):
        console.print(f"[red]Profile not found:[/red] {profile_id}")
        raise typer.Exit(1)
    if not yes:
        console.print(
            f"[yellow]Delete profile[/yellow] [bold]{profile_id}[/bold]? "
            "[dim](use --yes to skip confirmation)[/dim]"
        )
        if not typer.confirm("Continue?", default=False):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)
    delete_runner_profile(store, profile_id)
    console.print(f"[green]Deleted runner profile[/green] [bold]{profile_id}[/bold]")
