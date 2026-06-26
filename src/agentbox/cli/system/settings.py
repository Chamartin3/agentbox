"""system settings — list, show, and patch application settings."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from agentbox.cli.shared import console
from agentbox.core.service.system.service import SystemService

settings_app = typer.Typer(
    name="settings",
    help="List, show, and patch application settings.",
    no_args_is_help=True,
)


@settings_app.command("ls")
def settings_ls() -> None:
    """List all settings sections."""
    sections = SystemService().list_settings_sections()
    if not sections:
        console.print("[dim]no settings sections[/dim]")
        return
    for s in sections:
        console.print(f"[bold]{s}[/bold]")


@settings_app.command("show")
def settings_show(
    section: str = typer.Argument(..., help="Settings section name"),
) -> None:
    """Show settings for a section."""
    data = SystemService().get_settings_section(section)
    console.print(
        Panel(
            Syntax(json.dumps(data, indent=2, default=str), "json", theme="ansi_dark"),
            title=f"Settings — {section}",
        )
    )


@settings_app.command("patch")
def settings_patch(
    section: str = typer.Argument(..., help="Settings section name"),
    patch_json: str = typer.Argument(..., help="JSON object with key=value overrides"),
) -> None:
    """Patch settings for a section.

    Example:
        system settings patch general '{"log_level": "debug"}'
    """
    try:
        patch = json.loads(patch_json)
        if not isinstance(patch, dict):
            console.print("[red]patch must be a JSON object[/red]")
            raise typer.Exit(2)
    except json.JSONDecodeError as exc:
        console.print(f"[red]invalid JSON: {exc}[/red]")
        raise typer.Exit(2)

    SystemService().update_settings_section(section, patch)
    console.print(f"[green]patched[/green] section {section!r}")
