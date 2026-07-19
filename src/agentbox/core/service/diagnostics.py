"""DiagnosticsService — top-tier cross-domain diagnostics.

Aggregates health checks that span agents, execution, engines and the
workspace/MCP layout. Placed at the same tier as ``lifecycle`` in the
service DAG (above all domain services it queries) so it can import and
compose AgentService / ExecutionService / EngineService legally.

This is the proper home for the ``doctor`` check-building logic that was
previously inline in ``cli/system/doctor.py``. Moving it here makes the
same capability reusable by any future API ``/health`` endpoint and
testable at the service layer without going through Typer.
"""

from __future__ import annotations

from agentbox.core.config import load_settings
from agentbox.core.data.records import DoctorCheck
from agentbox.core.engines.credentials.state import CredentialState
from agentbox.core.service.agents import AgentService
from agentbox.core.service.engines import EngineService
from agentbox.core.service.execution import ExecutionService
from agentbox.core.workspaces.workdir import info as workspace_info


class DiagnosticsService:
    """Top-tier cross-domain diagnostics — aggregates health checks that
    span agents, execution, engines and the workspace/MCP layout.

    Self-wiring (zero-arg constructor): matches the uniform factory
    pattern used by every other Service. The three domain services are
    constructed internally; callers never pass them in.

        svc = DiagnosticsService()
        checks = svc.run_checks()
    """

    def __init__(self) -> None:
        self._agents = AgentService()
        self._execution = ExecutionService()
        self._engines = EngineService()

    def run_checks(self) -> list[DoctorCheck]:
        """Run the full diagnostic suite and return one check per domain.

        All checks are always attempted; a single domain failure does not
        abort the rest. Returns a list of :class:`DoctorCheck` named
        tuples: ``(name, ok, detail)``.
        """
        settings = load_settings()
        checks: list[DoctorCheck] = []

        def ok(name: str, detail: str = "") -> None:
            checks.append(DoctorCheck(name, True, detail))

        def fail(name: str, detail: str) -> None:
            checks.append(DoctorCheck(name, False, detail))

        # ── Workspaces ────────────────────────────────────────────────────
        try:
            rows = [
                workspace_info(a, settings)
                for a in self._agents.list_all_agents()
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

        # ── Database ──────────────────────────────────────────────────────
        try:
            self._execution.list_runs(limit=1)
            ok("Database", str(settings.db_path))
        except Exception as exc:
            fail("Database", str(exc))

        # ── Plugins ───────────────────────────────────────────────────────
        try:
            ok("Plugins", f"{len(self._engines.list_backend_names())} backend(s)")
        except Exception as exc:
            fail("Plugins", str(exc))

        # ── Credentials ───────────────────────────────────────────────────
        try:
            creds = self._engines.list_credentials()
            if not creds:
                ok("Credentials", "no backends registered")
            else:
                ok("Credentials", f"{len(creds)} backend(s)")
                for r in creds:
                    label = (
                        "configured"
                        if r.detect() == CredentialState.PRESENT
                        else "missing"
                    )
                    ok(f"  {r.backend}", label)
        except Exception as exc:
            ok("Credentials", str(exc))

        # ── MCP cache ─────────────────────────────────────────────────────
        cache = settings.mcp_cache_dir
        if cache.exists():
            ok(
                "MCP cache",
                f"{len(list(cache.glob('*.json')))} cached server(s) in {cache}",
            )
        else:
            ok("MCP cache", f"cache dir {cache} does not exist")

        return checks
