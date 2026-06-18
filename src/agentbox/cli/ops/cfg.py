from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.config import load_settings
from agentbox.core import workspaces as ws_mod
from agentbox.core.service.agents import list_all_agents

cfg_app = typer.Typer(
    name="cfg",
    help="Inspect resolved settings and generated runner configs.",
    no_args_is_help=True,
)


@cfg_app.command("show")
def cfg_show() -> None:
    """Show resolved Settings + AGENTBOX_* environment variables."""
    settings = load_settings()

    s_table = Table.grid(padding=(0, 2))
    s_table.add_column(style="dim", justify="right")
    s_table.add_column()
    for field in (
        "manifest_path",
        "data_dir",
        "db_path",
        "port",
        "host",
        "completion_webhook_url",
    ):
        val = getattr(settings, field, None)
        s_table.add_row(field, str(val) if val is not None else "—")
    for prop in (
        "project_root",
        "workspaces_root",
        "runs_dir",
        "sessions_dir",
        "mcp_cache_dir",
    ):
        val = getattr(settings, prop, None)
        s_table.add_row(prop, str(val) if val else "—")

    console.print(Panel(s_table, title="Settings", border_style="cyan"))

    env_table = Table.grid(padding=(0, 2))
    env_table.add_column(style="dim", width=50)
    env_table.add_column()
    for key in sorted(os.environ):
        if key.startswith("AGENTBOX_"):
            env_table.add_row(key, os.environ[key])
    console.print(
        Panel(env_table, title="AGENTBOX_* environment", border_style="green")
    )


@cfg_app.command("paths")
def cfg_paths() -> None:
    """Show all important paths as a tree."""
    settings = load_settings()
    tree = Tree(f"[bold]{settings.project_root}[/bold]")

    def _add(p: Path, parent: Tree, label: str | None = None) -> None:
        lbl = label or p.name
        if p.exists():
            size = p.stat().st_size if p.is_file() else 0
            suffix = f" ({size} bytes)" if size else ""
            parent.add(f"[green]{lbl}[/green]{suffix}")
        else:
            parent.add(f"[dim]{lbl}[/dim] · missing")

    _add(settings.manifest_path, tree, "manifest.toml")
    if settings.agents_dir:
        _add(settings.agents_dir, tree, "agents.d/")
    if settings.prompts_dir:
        _add(settings.prompts_dir, tree, "prompts.d/")
    if settings.skills_dir:
        _add(settings.skills_dir, tree, "skills.d/")
    if settings.outputs_dir:
        _add(settings.outputs_dir, tree, "outputs/")

    ws = tree.add("[bold]workspaces/[/bold]")
    for a in list_all_agents(store=get_store()):
        path, _eph = ws_mod.resolve_path(a, settings, get_store())
        _add(path, ws, a.id + (" [yellow](ephemeral)[/yellow]" if _eph else ""))

    data = tree.add("[bold]/data[/bold]")
    _add(settings.db_path, data, "agentbox.sqlite")
    _add(settings.runs_dir, data, "runs/")
    _add(settings.sessions_dir, data, "sessions/")
    _add(settings.mcp_cache_dir, data, "mcp_cache/")

    console.print(tree)
