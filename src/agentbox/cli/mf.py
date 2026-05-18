from __future__ import annotations

import typer
from rich.tree import Tree

from agentbox.cli._common import console
from agentbox.config import load_settings
from agentbox.core.deprecated.definitions import DefinitionLoader

mf_app = typer.Typer(
    name="mf",
    help="Inspect and validate the project manifest (agentbox.toml).",
    no_args_is_help=True,
)


@mf_app.command("show")
def mf_show() -> None:
    """Render the parsed manifest as a tree."""
    settings = load_settings()
    loader = DefinitionLoader(settings.project_root)
    manifest = loader._load_toml()

    tree = Tree(f"[bold]project:[/bold] {manifest.project}")

    if manifest.backend_preference:
        bp = ", ".join(manifest.backend_preference)
        tree.add(f"backend_preference: [{bp}]")

    agents_node = tree.add(f"agents ({len(manifest.agents)})")
    for a in manifest.agents:
        runner = a.runner.kind if a.runner else "?"
        ws_info = a.workspace or "[dim]auto[/dim]"
        agents_node.add(f"{a.id}  [cyan]{runner}[/cyan] · workspace={ws_info}")

    workspaces_node = tree.add(f"workspaces ({len(manifest.workspaces)})")
    for w in manifest.workspaces:
        workspaces_node.add(f"{w.name} → {w.path}")

    mcp_node = tree.add(f"mcp_servers ({len(manifest.mcp_servers)})")
    for s in manifest.mcp_servers:
        if s.url:
            mcp_node.add(f"{s.name}  [yellow](http {s.url})[/yellow]")
        elif s.command:
            cmd = " ".join(s.command)
            mcp_node.add(f"{s.name}  [yellow](stdio {cmd})[/yellow]")

    console.print(tree)


@mf_app.command("check")
def mf_check() -> None:
    """Validate the manifest; exit 1 on error. Suitable for CI."""
    settings = load_settings()
    loader = DefinitionLoader(settings.project_root)

    if not loader.manifest_path.exists():
        console.print(f"[red]manifest not found at {loader.manifest_path}[/red]")
        raise typer.Exit(1)

    try:
        loader.load()
        console.print("[green]✓[/green] manifest OK")
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None
