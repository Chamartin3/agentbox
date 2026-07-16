"""SystemService.doctor_checks — the diagnostic suite moved off the CLI.

The CLI command is now a thin caller (render + exit code); the checks live
on the service. This pins the returned shape and the clean-env verdicts.
"""

from __future__ import annotations

from agentbox.core.data import DoctorCheck
from agentbox.core.service.system import SystemService


def test_doctor_checks_returns_typed_results_and_passes_clean(
    system_service: SystemService,
) -> None:
    checks = system_service.doctor_checks()

    # Every result is a DoctorCheck (name, ok, detail) — no loose tuples.
    assert checks and all(isinstance(c, DoctorCheck) for c in checks)

    top = {c.name: c for c in checks if not c.name.startswith(" ")}
    # The suite always reports these top-level checks.
    assert {"Workspaces", "Database", "Plugins", "Credentials", "MCP cache"} <= set(top)
    # A fresh, isolated data dir has no failures.
    assert all(c.ok for c in checks)
    # Database check reports the configured sqlite path.
    assert "agentbox.sqlite" in top["Database"].detail


def test_doctor_checks_reports_database_failure(
    system_service: SystemService,
    monkeypatch,
) -> None:
    # Force the DB probe to raise → that one check fails, the aggregate still returns.
    import agentbox.core.service.execution as execution_mod

    def boom(self, **kwargs):  # noqa: ANN001, ANN003
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(execution_mod.ExecutionService, "list_runs", boom)

    checks = system_service.doctor_checks()
    db = next(c for c in checks if c.name == "Database")
    assert db.ok is False
    assert "db unreachable" in db.detail
