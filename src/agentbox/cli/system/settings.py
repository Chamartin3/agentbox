"""system settings — list, show, and patch application settings."""

from __future__ import annotations

import json

import typer

from agentbox.cli.shared import CLIContext

settings_app = typer.Typer(
    name="settings",
    help="List, show, and patch application settings.",
    no_args_is_help=True,
)


@settings_app.command("ls")
def settings_ls(ctx: typer.Context) -> None:
    """List all settings sections."""
    obj: CLIContext = ctx.obj
    sections = obj.system.list_settings_sections()
    obj.render.system.settings_sections_list(sections)


@settings_app.command("show")
def settings_show(
    ctx: typer.Context,
    section: str = typer.Argument(..., help="Settings section name"),
) -> None:
    """Show settings for a section."""
    obj: CLIContext = ctx.obj
    data = obj.system.get_settings_section(section)
    obj.render.system.settings_section_view(section, data)


@settings_app.command("patch")
def settings_patch(
    ctx: typer.Context,
    section: str = typer.Argument(..., help="Settings section name"),
    patch_json: str = typer.Argument(..., help="JSON object with key=value overrides"),
) -> None:
    """Patch settings for a section.

    Example:
        system settings patch general '{"log_level": "debug"}'
    """
    obj: CLIContext = ctx.obj
    try:
        patch = json.loads(patch_json)
        if not isinstance(patch, dict):
            obj.render.system.error("patch must be a JSON object")
            raise typer.Exit(2)
    except json.JSONDecodeError as exc:
        obj.render.system.error(f"invalid JSON: {exc}")
        raise typer.Exit(2)

    obj.system.update_settings_section(section, patch)
    obj.render.system.settings_patched(section)
