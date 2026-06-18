"""CLI commands for WorkenvConfig generation.

Usage:
    agentbox ops workenv generate --engine opencode --target-dir /tmp/my-env
    agentbox ops workenv generate my-workspace
    agentbox ops workenv generate --interactive
    agentbox ops workenv list-engines
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from typing import TYPE_CHECKING

import typer
from rich.syntax import Syntax

from agentbox.cli._common import console
from agentbox.cli._deps import get_settings, get_store
from agentbox.core.constants import BackendName
from agentbox.core.workspaces.generation.config import WorkenvConfig
from agentbox.core.workspaces.generation.builders.from_db import load_workenv
from agentbox.core.workspaces.generation.builders.from_yaml import load_from_yaml
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.builders.interactive import build_interactive
from agentbox.core.workspaces.generation.presets import (
    from_preset,
    list_presets,
    save_as_preset,
    seed_presets,
)
from agentbox.core.workspaces.generation.recipe import Recipe, list_recipes, load_recipe
from agentbox.core.service.workspaces.files import resolve_workspace_path
from agentbox.core.service.workspaces.permissions import load_effective_permissions

if TYPE_CHECKING:
    from agentbox.core.config import Settings
    from agentbox.core.db import SessionStore

workenv_app = typer.Typer(
    name="workenv",
    help="Generate workspace config files from WorkenvConfig.",
    no_args_is_help=True,
)


@dataclass
class _ResolvedSource:
    config: WorkenvConfig
    engine: str
    target_dir: Path
    source_label: str


@workenv_app.command("generate")
def workenv_generate(
    name: str | None = typer.Argument(
        None, help="Workspace name or agent ID (omit for interactive)"
    ),
    engine: str = typer.Option(
        BackendName.CLAUDE_CODE,
        "--engine",
        "-e",
        help=f"Recipe engine to use ({', '.join(BackendName.values())})",
    ),
    target_dir: str | None = typer.Option(
        None,
        "--target-dir",
        "-t",
        help="Target directory (default: the workspace's workdir)",
    ),
    config_file: str | None = typer.Option(
        None,
        "--config-file",
        "-f",
        help="Path to a YAML WorkenvConfig file (skips DB loading)",
    ),
    preset: str | None = typer.Option(
        None,
        "--preset",
        "-p",
        help="Load from a named preset (requires Phase G)",
    ),
    save: str | None = typer.Option(
        None,
        "--save",
        "-s",
        help="Save as a named workspace after generation (requires Phase G)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print generated files to stdout instead of writing",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Force interactive mode even when name is provided",
    ),
) -> None:
    """Generate workspace config files using a recipe engine.

    Loads configuration from the DB (by name), from a YAML file
    (--config-file), from a preset (--preset), or interactively
    (no arguments or --interactive).
    """
    store = get_store()
    settings = get_settings()

    source = _resolve_source(
        name=name,
        engine=engine,
        target_dir=target_dir,
        config_file=config_file,
        preset=preset,
        interactive=interactive,
        store=store,
        settings=settings,
    )

    available = list_recipes()
    if source.engine not in available:
        console.print(
            f"[red]unknown engine {source.engine!r}[/red] — "
            f"available: {', '.join(available)}"
        )
        raise typer.Exit(1)

    recipe = load_recipe(source.engine)
    source.target_dir.mkdir(parents=True, exist_ok=True)

    if save is not None:
        save_as_preset(
            store,
            save,
            source.config,
            engine=source.engine,
            description=f"Saved from CLI ({source.source_label})",
        )
        console.print(f"[green]saved[/green] preset [bold]{save}[/bold]")

    if dry_run:
        _print_dry_run(source.config, recipe)
        return

    result = render(source.target_dir, source.config, recipe)
    console.print(
        f"[green]generated[/green] {len(result.written_paths)} file(s) "
        f"in [bold]{source.target_dir}[/bold]"
    )
    for p in result.written_paths:
        console.print(f"  [dim]{p.relative_to(source.target_dir)}[/dim]")

    if source.source_label == "interactive":
        console.print(
            "\n[dim]Tip: use --config-file or --save to persist this config.[/dim]"
        )


def _resolve_source(
    *,
    name: str | None,
    engine: str,
    target_dir: str | None,
    config_file: str | None,
    preset: str | None,
    interactive: bool,
    store: SessionStore,
    settings: Settings,
) -> _ResolvedSource:
    """Resolve config, engine, and target dir from CLI inputs."""
    if preset is not None:
        config = from_preset(store, preset)
        if config is None:
            console.print(f"[red]preset not found:[/red] {preset}")
            raise typer.Exit(1)
        out_dir = _resolve_target_dir(target_dir, name, store, settings)
        return _ResolvedSource(config, engine, out_dir, "preset")

    if config_file is not None:
        config_path = Path(config_file)
        if not config_path.is_file():
            console.print(f"[red]config file not found:[/red] {config_file}")
            raise typer.Exit(1)
        config = load_from_yaml(config_path)
        out_dir = _resolve_target_dir(target_dir, name, store, settings)
        return _ResolvedSource(config, engine, out_dir, "yaml")

    if interactive or name is None:
        config, chosen_engine, chosen_dir = build_interactive()
        return _ResolvedSource(config, chosen_engine, chosen_dir, "interactive")

    perms = load_effective_permissions(
        name,
        store=store,
        settings=settings,
        loader=None,
        mcp_manifest=None,
    )
    config = load_workenv(store, name, settings=settings, permissions=perms)
    out_dir = _resolve_target_dir(target_dir, name, store, settings)
    return _ResolvedSource(config, engine, out_dir, "db")


def _resolve_target_dir(
    target_dir: str | None,
    name: str | None,
    store: SessionStore,
    settings: Settings,
) -> Path:
    if target_dir is not None:
        return Path(target_dir)
    if name is not None:
        ws_path, _project_root = resolve_workspace_path(
            name, store=store, settings=settings, loader=None
        )
        return ws_path
    return Path.cwd() / "out"


@workenv_app.command("seed-presets")
def workenv_seed_presets() -> None:
    """Load built-in presets into the DB (idempotent)."""
    store = get_store()
    count = seed_presets(store)
    console.print(f"[green]seeded[/green] {count} preset(s)")


@workenv_app.command("list-presets")
def workenv_list_presets() -> None:
    """List saved presets in the DB."""
    store = get_store()
    presets = list_presets(store)
    if not presets:
        console.print("[yellow]No presets saved[/yellow]")
        return
    console.print("Available presets:")
    for p in presets:
        desc = p.get("description", "") or ""
        engine = p.get("engine", "?")
        console.print(
            f"  [bold]{p['name']}[/bold]  [dim]({engine})[/dim]  {desc}"
        )


@workenv_app.command("list-engines")
def workenv_list_engines() -> None:
    """List available recipe engines."""
    available = list_recipes()
    if not available:
        console.print("[yellow]No recipes found[/yellow]")
        return
    console.print("Available engines:")
    for r in available:
        console.print(f"  [bold]{r}[/bold]")


def _print_dry_run(config: WorkenvConfig, recipe: Recipe) -> None:
    """Print rendered output to stdout instead of writing to disk."""
    with tempfile.TemporaryDirectory() as td:
        result = render(Path(td), config, recipe)
        for p in result.written_paths:
            rel = p.relative_to(Path(td))
            content = p.read_text(encoding="utf-8")
            console.print(f"\n[bold cyan]─── {rel}[/bold cyan]")
            syntax = Syntax(
                content,
                "json" if rel.suffix == ".json"
                else "yaml" if rel.suffix in (".yaml", ".yml")
                else "markdown",
                theme="ansi_dark",
            )
            console.print(syntax)
