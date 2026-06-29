"""CLI commands for WorkenvConfig generation.

Usage:
    agentbox ops workenv generate --engine opencode --target-dir /tmp/my-env
    agentbox ops workenv generate my-workspace
    agentbox ops workenv generate --interactive
    agentbox ops workenv list-engines
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.config import Settings
from agentbox.core.constants import BackendName
from agentbox.core.service import WorkspaceService
from agentbox.core.workspaces.generation.config import WorkenvConfig
from agentbox.core.workspaces.generation.builders.from_yaml import load_from_yaml
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.workspaces.generation.builders.interactive import build_interactive
from agentbox.core.workspaces.generation.recipe import list_recipes, load_recipe

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
    ctx: typer.Context,
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
    obj: CLIContext = ctx.obj
    settings = obj.settings
    svc = WorkspaceService()

    try:
        source = _resolve_source(
            name=name,
            engine=engine,
            target_dir=target_dir,
            config_file=config_file,
            preset=preset,
            interactive=interactive,
            svc=svc,
            settings=settings,
        )
    except ValueError as exc:
        obj.render.ops.error(str(exc))
        raise typer.Exit(1) from exc

    available = list_recipes()
    if source.engine not in available:
        obj.render.ops.error(
            f"unknown engine {source.engine!r} — "
            f"available: {', '.join(available)}"
        )
        raise typer.Exit(1)

    recipe = load_recipe(source.engine)
    source.target_dir.mkdir(parents=True, exist_ok=True)

    if save is not None:
        svc.save_workenv_as_preset(
            save,
            source.config,
            engine=source.engine,
            description=f"Saved from CLI ({source.source_label})",
        )
        obj.render.ops.success(f"saved preset [bold]{save}[/bold]")

    if dry_run:
        obj.render.ops.workenv_preview(source.config, recipe)
        return

    result = render(source.target_dir, source.config, recipe)
    obj.render.ops.success(
        f"generated {len(result.written_paths)} file(s) "
        f"in {source.target_dir}"
    )
    for p in result.written_paths:
        obj.render.ops.dim(f"  {p.relative_to(source.target_dir)}")

    if source.source_label == "interactive":
        obj.render.ops.dim(
            "\nTip: use --config-file or --save to persist this config."
        )


def _resolve_source(
    *,
    name: str | None,
    engine: str,
    target_dir: str | None,
    config_file: str | None,
    preset: str | None,
    interactive: bool,
    svc: WorkspaceService,
    settings: Settings,
) -> _ResolvedSource:
    """Resolve config, engine, and target dir from CLI inputs.

    Raises ``ValueError`` on user-facing errors; caller prints and exits.
    """
    if preset is not None:
        config = svc.workenv_from_preset(preset)
        if config is None:
            raise ValueError(f"preset not found: {preset}")
        out_dir = _resolve_target_dir(target_dir, name, svc, settings)
        return _ResolvedSource(config, engine, out_dir, "preset")

    if config_file is not None:
        config_path = Path(config_file)
        if not config_path.is_file():
            raise ValueError(f"config file not found: {config_file}")
        config = load_from_yaml(config_path)
        out_dir = _resolve_target_dir(target_dir, name, svc, settings)
        return _ResolvedSource(config, engine, out_dir, "yaml")

    if interactive or name is None:
        config, chosen_engine, chosen_dir = build_interactive()
        return _ResolvedSource(config, chosen_engine, chosen_dir, "interactive")

    perms = svc.load_effective_permissions(name)
    config = svc.load_workenv(name, settings=settings, permissions=perms)
    out_dir = _resolve_target_dir(target_dir, name, svc, settings)
    return _ResolvedSource(config, engine, out_dir, "db")


def _resolve_target_dir(
    target_dir: str | None,
    name: str | None,
    svc: WorkspaceService,
    settings: Settings,
) -> Path:
    if target_dir is not None:
        return Path(target_dir)
    if name is not None:
        ws_path, _project_root = svc.resolve_workspace_path(name, settings=settings)
        return ws_path
    return Path.cwd() / "out"


@workenv_app.command("seed-presets")
def workenv_seed_presets(ctx: typer.Context) -> None:
    """Load built-in presets into the DB (idempotent)."""
    obj: CLIContext = ctx.obj
    count = WorkspaceService().seed_presets()
    obj.render.ops.success(f"seeded {count} preset(s)")


@workenv_app.command("list-presets")
def workenv_list_presets(ctx: typer.Context) -> None:
    """List saved presets in the DB."""
    obj: CLIContext = ctx.obj
    presets = WorkspaceService().list_presets()
    if not presets:
        obj.render.ops.warn("No presets saved")
        return
    obj.render.ops.dim("Available presets:")
    for p in presets:
        desc = p.get("description", "") or ""
        engine = p.get("engine", "?")
        obj.render.ops.dim(f"  {p['name']}  ({engine})  {desc}")


@workenv_app.command("list-engines")
def workenv_list_engines(ctx: typer.Context) -> None:
    """List available recipe engines."""
    obj: CLIContext = ctx.obj
    available = list_recipes()
    if not available:
        obj.render.ops.warn("No recipes found")
        return
    obj.render.ops.dim("Available engines:")
    for r in available:
        obj.render.ops.dim(f"  {r}")
