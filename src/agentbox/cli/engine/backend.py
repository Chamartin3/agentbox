"""Runner backend discovery CLI — list registered backend adapters."""

from __future__ import annotations

import json as _json

import typer
from rich.table import Table

from agentbox.cli.shared import console
from agentbox.core.constants import BackendName
from agentbox.core.service.engines import EngineService

app = typer.Typer(
    name="backends",
    help="List registered backend adapters and compatible providers.",
    no_args_is_help=True,
)

_LABELS: dict[str, str] = {
    BackendName.CLAUDE_CODE: "Claude Code (CLI)",
    BackendName.OPENCODE: "OpenCode (CLI)",
    BackendName.CODEX: "OpenAI Codex (CLI)",
    BackendName.PI: "pi.dev (CLI)",
    BackendName.TOKEN: "Token / pydantic-ai (in-process)",
}


@app.command("ls")
def backend_ls(
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List every registered backend along with compatible providers."""
    svc = EngineService()
    providers = svc.list_providers()
    rows = sorted(svc.backends().items())
    if not rows:
        console.print("[yellow]No backends registered.[/yellow]")
        return

    if json_output:
        result = []
        for name, cls in rows:
            compatible = [p.id for p in providers if name in (p.compatible_backends or [])]
            result.append({
                "id": name,
                "label": _LABELS.get(name, name),
                "default_model": getattr(cls, "default_model", None),
                "compatible_providers": compatible,
            })
        console.print(_json.dumps(result, indent=2))
        return

    table = Table(
        title="Runner Backends",
        title_style="bold",
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("ID", style="bold")
    table.add_column("Label", style="cyan")
    table.add_column("Default Model", style="dim")
    table.add_column("Compatible Providers", style="dim")

    for name, cls in rows:
        compatible = [p.id for p in providers if name in (p.compatible_backends or [])]
        table.add_row(
            name,
            _LABELS.get(name, name),
            getattr(cls, "default_model", None) or "—",
            ", ".join(compatible) if compatible else "—",
        )

    console.print(table)
