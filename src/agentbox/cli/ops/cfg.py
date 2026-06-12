from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from agentbox.cli._deps import get_store
from agentbox.cli._common import console
from agentbox.config import load_settings
from agentbox.core import workspaces as ws_mod
from agentbox.core.service.agents import list_all_agents
from agentbox.core.service.workspaces import generate_legacy_runner_configs
from agentbox.core.workspaces.mcp.client import McpRegistry

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


@cfg_app.command("gen")
def cfg_gen(
    agent: str | None = typer.Option(None, "--agent", help="Filter to a single agent"),
) -> None:
    """Generate runner configs into a temp dir and print the JSON (diagnostic dry-run)."""
    settings = load_settings()
    all_agents = list_all_agents(store=get_store())
    if agent is not None:
        target_agents = [a for a in all_agents if a.id == agent]
        if not target_agents:
            console.print(f"[red]unknown agent[/red] {agent!r}")
            raise typer.Exit(2)
    else:
        target_agents = all_agents

    if not target_agents:
        console.print("[yellow]No agents to generate configs for.[/yellow]")
        return

    mcp_registry = McpRegistry(settings.mcp_cache_dir)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        result = generate_legacy_runner_configs(
            tmp,
            store=get_store(),
            settings=settings,
            mcp_registry=mcp_registry,
        )

        for config_type, filepath in result.items():
            if filepath.exists():
                data = json.loads(filepath.read_text(encoding="utf-8"))
                console.print(
                    f"\n[bold cyan]─── {config_type}[/bold cyan]  [dim]{filepath.name}[/dim]"
                )
                console.print(
                    Syntax(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        "json",
                        theme="ansi_dark",
                    )
                )
