"""Runner provider CLI commands — list providers and query models."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.service.engines import ProfileNotFound  # TODO(cli-arch): move to facade export

app = typer.Typer(
    name="providers",
    help="List providers and query available models.",
    no_args_is_help=True,
)


@app.command("ls")
def provider_ls(ctx: typer.Context) -> None:
    """List available provider descriptors."""
    obj: CLIContext = ctx.obj
    descriptors = obj.engines.list_providers()
    obj.render.engine.providers_table(descriptors)


@app.command("models")
def provider_models(
    ctx: typer.Context,
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
    obj: CLIContext = ctx.obj

    if profile_id:
        try:
            profile = obj.engines.get_profile(profile_id)
        except ProfileNotFound:
            obj.render.engine.error(f"Profile not found: {profile_id}")
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

    provider = obj.engines.get_provider(provider_id)
    if not provider:
        obj.render.engine.provider_not_found(provider_id)
        raise typer.Exit(1)

    if not provider.descriptor.supports_model_listing:
        obj.render.engine.provider_models_not_supported(provider_id)
        raise typer.Exit(1)

    try:
        models = asyncio.run(
            obj.engines.list_provider_models_raw(provider_id, config, refresh=refresh)
        )
    except Exception as exc:
        obj.render.engine.provider_models_error(str(exc))
        raise typer.Exit(1)  # noqa: B904

    obj.render.engine.provider_models_table(provider_id, models)


@app.command("refresh")
def provider_refresh(ctx: typer.Context) -> None:
    """Re-discover dynamic providers (currently: opencode CLI)."""
    obj: CLIContext = ctx.obj
    discovered = obj.engines.refresh_opencode_providers()
    if not discovered:
        obj.render.engine.provider_refresh_none()
        return
    obj.render.engine.provider_refresh_success(discovered)
