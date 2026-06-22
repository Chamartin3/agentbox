"""system settings — list, show, and patch application settings."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from agentbox.cli.shared import console, get_store
from agentbox.core.service import (
    get_settings_section,
    list_settings_sections,
    update_settings_section,
)

setting_app = typer.Typer(
    name="setting",
    help="List, show, and patch application settings.",
    no_args_is_help=True,
)


@setting_app.command("ls")
def settings_ls() -> None:
    """List all settings sections."""
    store = get_store()
    sections = list_settings_sections(store)
    if not sections:
        console.print("[dim]no settings sections[/dim]")
        return
    for s in sections:
        console.print(f"[bold]{s}[/bold]")


@setting_app.command("show")
def settings_show(
    section: str = typer.Argument(..., help="Settings section name"),
) -> None:
    """Show settings for a section."""
    store = get_store()
    data = get_settings_section(store, section)
    console.print(
        Panel(
            Syntax(json.dumps(data, indent=2, default=str), "json", theme="ansi_dark"),
            title=f"Settings — {section}",
        )
    )


@setting_app.command("patch")
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

    store = get_store()
    update_settings_section(store, section, patch)
    console.print(f"[green]patched[/green] section {section!r}")
