"""Runner profile CLI commands — create, list, bind, stats, delete."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.service import RunnerProfileCreate
from agentbox.core.service.engines import ProfileNotFound  # TODO(cli-arch): move to facade export

app = typer.Typer(
    name="profiles",
    help="Manage runner profiles (create, list, bind to agents).",
    no_args_is_help=True,
)


@app.command("ls")
def profile_ls(
    ctx: typer.Context,
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
    obj: CLIContext = ctx.obj
    profiles = obj.engines.list_profiles(backend=backend, provider=provider, enabled=enabled)

    if json_output:
        obj.render.engine.profiles_json(profiles)
    else:
        obj.render.engine.profiles_table(profiles)


@app.command("show")
def profile_get(
    ctx: typer.Context,
    profile_id: str,
) -> None:
    """Show runner profile details as JSON."""
    obj: CLIContext = ctx.obj
    try:
        profile = obj.engines.get_profile(profile_id)
    except ProfileNotFound:
        obj.render.engine.profile_not_found(profile_id)
        raise typer.Exit(1)

    obj.render.engine.profile_detail_json(profile)


@app.command("new")
def profile_create(
    ctx: typer.Context,
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
    obj: CLIContext = ctx.obj
    profile = obj.engines.create_profile(
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
    obj.render.engine.profile_created(profile)


@app.command("bind")
def profile_bind(
    ctx: typer.Context,
    agent_id: str = typer.Argument(..., help="Agent ID"),
    profile_id: str = typer.Argument(
        None, help="Runner profile ID (omit with --clear to unbind)"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Remove the profile binding from the agent"
    ),
) -> None:
    """Bind a runner profile to an agent, or clear it with --clear."""
    obj: CLIContext = ctx.obj
    if clear:
        obj.engines.clear_agent_runner_profile(agent_id)
        obj.render.engine.profile_cleared(agent_id)
        return
    if not profile_id:
        obj.render.engine.error("Either provide a profile_id or use --clear")
        raise typer.Exit(2)
    try:
        obj.engines.set_agent_runner_profile(agent_id, profile_id)
    except ProfileNotFound as exc:
        obj.render.engine.error(str(exc))
        raise typer.Exit(1)
    obj.render.engine.profile_bound(agent_id, profile_id)


@app.command("stats")
def profile_stats(
    ctx: typer.Context,
    profile_id: str | None = typer.Argument(
        None, help="Profile ID (optional; if omitted, lists all)"
    ),
) -> None:
    """Show per-profile statistics."""
    obj: CLIContext = ctx.obj

    if profile_id:
        stats = obj.engines.get_profile_stats(profile_id)
        obj.render.engine.profile_stats_detail(profile_id, stats)
        return

    all_stats = obj.engines.list_profile_stats()
    obj.render.engine.all_profile_stats_table(all_stats)


@app.command("rm")
def profile_delete(
    ctx: typer.Context,
    profile_id: str = typer.Argument(..., help="Profile ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Delete a runner profile."""
    obj: CLIContext = ctx.obj
    try:
        obj.engines.get_profile(profile_id)  # check existence
    except ProfileNotFound:
        obj.render.engine.profile_not_found(profile_id)
        raise typer.Exit(1)
    if not yes:
        obj.render.engine.warn(
            f"Delete profile [bold]{profile_id}[/bold]? "
            "[dim](use --yes to skip confirmation)[/dim]"
        )
        if not typer.confirm("Continue?", default=False):
            obj.render.engine.dim("Aborted.")
            raise typer.Exit(0)
    obj.engines.delete_profile(profile_id)
    obj.render.engine.profile_deleted(profile_id)
