"""Doctor command — run a suite of diagnostic checks.

Cross-domain aggregation lives here in the interface layer: it reads every
domain through the context-injected services (``obj.<svc>``). No service is
constructed here, and no domain code is imported.
"""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext
from agentbox.core.service import CredentialState, DoctorCheck
from agentbox.core.service import info as workspace_info


def doctor(ctx: typer.Context) -> None:
    """Run a suite of diagnostic checks and print the results."""
    obj: CLIContext = ctx.obj
    settings = obj.settings
    checks: list[DoctorCheck] = []

    def ok(name: str, detail: str = "") -> None:
        checks.append(DoctorCheck(name, True, detail))

    def fail(name: str, detail: str) -> None:
        checks.append(DoctorCheck(name, False, detail))

    try:
        rows = [workspace_info(a, settings) for a in obj.agents.list_all_agents()]
        resolvable = True
        for w in rows:
            if not w.exists and not w.ephemeral:
                resolvable = False
                ok("Workspaces", f"{w.agent_id}: path {w.path} does not exist")
        if resolvable:
            ok("Workspaces", f"{len(rows)} agent(s), all paths resolvable")
    except Exception as exc:
        fail("Workspaces", str(exc))

    try:
        obj.execution.list_runs(limit=1)
        ok("Database", str(settings.db_path))
    except Exception as exc:
        fail("Database", str(exc))

    try:
        ok("Plugins", f"{len(obj.engines.list_backend_names())} backend(s)")
    except Exception as exc:
        fail("Plugins", str(exc))

    try:
        creds = obj.engines.list_credentials()
        if not creds:
            ok("Credentials", "no backends registered")
        else:
            ok("Credentials", f"{len(creds)} backend(s)")
            for r in creds:
                label = "configured" if r.detect() == CredentialState.PRESENT else "missing"
                ok(f"  {r.backend}", label)
    except Exception as exc:
        ok("Credentials", str(exc))

    cache = settings.mcp_cache_dir
    if cache.exists():
        ok("MCP cache", f"{len(list(cache.glob('*.json')))} cached server(s) in {cache}")
    else:
        ok("MCP cache", f"cache dir {cache} does not exist")

    obj.render.system.doctor_report(checks)
    raise typer.Exit(1 if any(not c.ok for c in checks) else 0)
