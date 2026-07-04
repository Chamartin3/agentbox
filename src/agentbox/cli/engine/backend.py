"""Runner backend discovery CLI — list registered backend adapters."""

from __future__ import annotations

import typer
from agentbox.cli.shared import CLIContext
from agentbox.core.data.constants import BackendName

app = typer.Typer(
    name="backends",
    help="List registered backend adapters and compatible providers.",
    no_args_is_help=True,
)


@app.command("ls")
def backend_ls(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON instead of a table"
    ),
) -> None:
    """List every registered backend along with compatible providers."""
    obj: CLIContext = ctx.obj
    providers = obj.engines.list_providers()
    backends = sorted(obj.engines.backends().items())
    rows: list[tuple[str, str, str | None, str | None]] = []
    for name, cls in backends:
        compatible: list[str] = [p.id for p in providers if name in (p.compatible_backends or [])]
        default_model: str | None = getattr(cls, "default_model", None)
        compat_str: str | None = ", ".join(compatible) if compatible else None
        rows.append((
            name,
            BackendName.label_for(name),
            default_model,
            compat_str,
        ))

    if json_output:
        obj.render.engine.backends_json(rows)
    else:
        obj.render.engine.backends_table(rows)
