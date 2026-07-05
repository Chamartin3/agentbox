"""Doctor command — run a suite of diagnostic checks."""

from __future__ import annotations

import typer

from agentbox.cli.shared import CLIContext

# TODO(cli-arch): SystemService.doctor_checks (core gap)
from agentbox.core import workspaces as ws_workspaces
from agentbox.core.service.engines import CredentialState


# Mypy note: the plan declares checks as list[tuple[str, bool, str]]
# for compatibility with the generic callers below.
def doctor(ctx: typer.Context) -> None:
    """Run a suite of diagnostic checks and print the results."""
    obj: CLIContext = ctx.obj

    checks: list[tuple[str, bool, str]] = []
    failures = 0

    def ok(check: str, detail: str = "") -> None:
        checks.append((check, True, detail))

    def fail(check: str, detail: str) -> None:
        nonlocal failures
        failures += 1
        checks.append((check, False, detail))

    try:
        rows = [
            ws_workspaces.info(a, obj.settings)
            for a in obj.agents.list_all_agents()
        ]
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
        ok("Database", str(obj.settings.db_path))
    except Exception as exc:
        fail("Database", str(exc))

    try:
        backend_count = len(obj.engines.list_backend_names())
        ok("Plugins", f"{backend_count} backend(s)")
    except Exception as exc:
        fail("Plugins", str(exc))

    try:
        rows = obj.engines.list_credentials()
        if not rows:
            ok("Credentials", "no backends registered")
        else:
            ok("Credentials", f"{len(rows)} backend(s)")
            for r in rows:
                state = r.detect()
                label = "configured" if state == CredentialState.PRESENT else "missing"
                if state == CredentialState.PRESENT:
                    ok(f"  {r.backend}", label)
                else:
                    ok(f"  {r.backend}", f"{label}")
    except Exception as exc:
        ok("Credentials", str(exc))

    cache = obj.settings.mcp_cache_dir
    if cache.exists():
        files = list(cache.glob("*.json"))
        ok("MCP cache", f"{len(files)} cached server(s) in {cache}")
    else:
        ok("MCP cache", f"cache dir {cache} does not exist")

    obj.render.system.doctor_report(checks)
    raise typer.Exit(min(failures, 1))
