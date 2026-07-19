"""Doctor command — run a suite of diagnostic checks.

Delegates to ``DiagnosticsService.run_checks()`` for the check-building
logic. This command is a thin presentation shell: call the service, render
the table, exit 1 if any check failed.
"""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext


def doctor(ctx: typer.Context) -> None:
    """Run a suite of diagnostic checks and print the results."""
    obj: CLIContext = ctx.obj
    checks = obj.diagnostics.run_checks()
    obj.render.system.doctor_report(checks)
    raise typer.Exit(1 if any(not c.ok for c in checks) else 0)
