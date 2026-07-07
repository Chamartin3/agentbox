"""Interactive builder — guides the user through building a WorkenvConfig.

Uses Rich console for output and ``rich.prompt`` for prompting.
Each prompt populates one field on the in-memory WorkenvConfig.
The CLI never assembles fragments by hand — it calls this builder
and hands the result to the generator.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from agentbox.core.data.workenv import (
    Permissions,
    WorkenvConfig,
)

_console = Console()


def build_interactive(
    *,
    engine: str | None = None,
    target_dir: str | None = None,
    available_engines: list[str] | None = None,
) -> tuple[WorkenvConfig, str, Path]:
    """Run interactive prompts to build a WorkenvConfig.

    Returns the constructed WorkenvConfig, the chosen engine name,
    and the target directory path.

    *available_engines* is required when *engine* is ``None``; it is
    supplied by the caller (e.g. ``WorkspaceService.list_recipe_engines()``)
    so that this module has no import dependency on the backend registry.
    """
    _console.print("\n[bold]WorkenvConfig Interactive Builder[/bold]\n")

    name = Prompt.ask("[bold]Workspace name[/bold]", default="my-workspace")
    description = Prompt.ask("[bold]Description[/bold]", default="")
    config = WorkenvConfig(
        name=name,
        description=description,
        permissions=Permissions(data={}),
    )

    if engine is None:
        engine = _prompt_engine(available_engines)
    if target_dir is None:
        target_dir = _prompt_target_dir()

    out_dir = Path(target_dir)
    return config, engine, out_dir


def _prompt_engine(available: list[str] | None = None) -> str:
    if not available:
        _console.print("[red]No recipes found — cannot generate[/red]")
        raise SystemExit(1)
    _console.print("[bold]Engine:[/bold]")
    for i, eng in enumerate(available, 1):
        _console.print(f"  {i}) {eng}")
    default_idx = "1"
    choice = Prompt.ask("  Choose", default=default_idx)
    try:
        idx = int(choice) - 1
        return available[idx]
    except (ValueError, IndexError):
        _console.print(f"[red]Invalid choice, using {available[0]}[/red]")
        return available[0]


def _prompt_target_dir() -> str:
    default = "./workenv-out"
    return Prompt.ask("[bold]Target directory[/bold]", default=default)
