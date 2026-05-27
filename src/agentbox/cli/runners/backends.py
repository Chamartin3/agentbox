"""Runner backend discovery CLI — list registered backend adapters."""

from __future__ import annotations

import typer
from rich.table import Table

from agentbox.cli._common import console
from agentbox.core.agent.plugins import backends as registered_backends
from agentbox.core.agent.providers import list_providers

app = typer.Typer(
    name="backends",
    help="List registered backend adapters and compatible providers.",
    no_args_is_help=True,
)

_LABELS: dict[str, str] = {
    "claude_code": "Claude Code (CLI)",
    "opencode": "OpenCode (CLI)",
    "codex": "OpenAI Codex (CLI)",
    "pi": "pi.dev (CLI)",
    "token": "Token / pydantic-ai (in-process)",
}


@app.command("ls")
def backend_ls() -> None:
    """List every registered backend along with compatible providers."""
    providers = list_providers()
    rows = sorted(registered_backends().items())
    if not rows:
        console.print("[yellow]No backends registered.[/yellow]")
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
