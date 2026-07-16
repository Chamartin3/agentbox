"""Doctor command — run a suite of diagnostic checks."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext


def doctor(ctx: typer.Context) -> None:
    """Run a suite of diagnostic checks and print the results."""
    obj: CLIContext = ctx.obj

    checks = obj.system.doctor_checks()
    obj.render.system.doctor_report(checks)
    raise typer.Exit(1 if any(not c.ok for c in checks) else 0)
