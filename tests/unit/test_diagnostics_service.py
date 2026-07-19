"""Tests for ``core.service.diagnostics.DiagnosticsService``.

Exercises ``run_checks()`` at the service layer without going through
Typer or the CLI — verifying typed results, a clean-env all-pass, and
a forced DB-probe failure that surfaces the right check.

All integration dependencies (AgentService / ExecutionService /
EngineService / workspace_info) are patched so no DB, filesystem, or
subprocess is touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentbox.core.data.records import DoctorCheck
from agentbox.core.engines.credentials.state import CredentialState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    *,
    agents: MagicMock,
    execution: MagicMock,
    engines: MagicMock,
) -> "DiagnosticsService":  # noqa: F821
    """Construct a DiagnosticsService with pre-built mock sub-services."""
    from agentbox.core.service.diagnostics import DiagnosticsService

    svc = DiagnosticsService.__new__(DiagnosticsService)
    svc._agents = agents
    svc._execution = execution
    svc._engines = engines
    return svc


def _mock_settings(tmp_path: "Path") -> MagicMock:  # noqa: F821
    s = MagicMock()
    s.db_path = tmp_path / "agentbox.db"
    s.mcp_cache_dir = tmp_path / "mcp_cache"
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_checks_returns_list_of_doctor_checks(tmp_path) -> None:
    """run_checks() always returns a list[DoctorCheck]."""
    agents = MagicMock()
    agents.list_all_agents.return_value = []

    execution = MagicMock()
    execution.list_runs.return_value = []

    engines = MagicMock()
    engines.list_backend_names.return_value = []
    engines.list_credentials.return_value = []

    svc = _make_service(agents=agents, execution=execution, engines=engines)

    with patch(
        "agentbox.core.service.diagnostics.load_settings",
        return_value=_mock_settings(tmp_path),
    ), patch(
        "agentbox.core.service.diagnostics.workspace_info",
    ):
        checks = svc.run_checks()

    assert isinstance(checks, list)
    assert all(isinstance(c, DoctorCheck) for c in checks)
    # Always emits at least the named checks
    names = {c.name for c in checks}
    assert "Workspaces" in names
    assert "Database" in names
    assert "Plugins" in names
    assert "Credentials" in names
    assert "MCP cache" in names


def test_run_checks_all_pass_clean_env(tmp_path) -> None:
    """Clean environment → every check passes (ok=True)."""
    agents = MagicMock()
    agents.list_all_agents.return_value = []

    execution = MagicMock()
    execution.list_runs.return_value = []

    engines = MagicMock()
    engines.list_backend_names.return_value = ["claude_code"]
    engines.list_credentials.return_value = []

    svc = _make_service(agents=agents, execution=execution, engines=engines)

    with patch(
        "agentbox.core.service.diagnostics.load_settings",
        return_value=_mock_settings(tmp_path),
    ), patch(
        "agentbox.core.service.diagnostics.workspace_info",
    ):
        checks = svc.run_checks()

    failed = [c for c in checks if not c.ok]
    assert failed == [], f"Expected no failures, got: {failed}"


def test_run_checks_db_failure_surfaces_one_failed_check(tmp_path) -> None:
    """When ExecutionService.list_runs raises, the Database check fails."""
    agents = MagicMock()
    agents.list_all_agents.return_value = []

    execution = MagicMock()
    execution.list_runs.side_effect = RuntimeError("disk full")

    engines = MagicMock()
    engines.list_backend_names.return_value = []
    engines.list_credentials.return_value = []

    svc = _make_service(agents=agents, execution=execution, engines=engines)

    with patch(
        "agentbox.core.service.diagnostics.load_settings",
        return_value=_mock_settings(tmp_path),
    ), patch(
        "agentbox.core.service.diagnostics.workspace_info",
    ):
        checks = svc.run_checks()

    db_checks = [c for c in checks if c.name == "Database"]
    assert len(db_checks) == 1
    assert db_checks[0].ok is False
    assert "disk full" in db_checks[0].detail

    # Other checks still ran — workspace check should still be present and ok
    ws_checks = [c for c in checks if c.name == "Workspaces"]
    assert len(ws_checks) == 1
    assert ws_checks[0].ok is True


def test_run_checks_credential_detection(tmp_path) -> None:
    """Credential lines reflect PRESENT / missing state from detect()."""
    agents = MagicMock()
    agents.list_all_agents.return_value = []

    execution = MagicMock()
    execution.list_runs.return_value = []

    cred_present = MagicMock()
    cred_present.backend = "claude_code"
    cred_present.detect.return_value = CredentialState.PRESENT

    cred_missing = MagicMock()
    cred_missing.backend = "opencode"
    cred_missing.detect.return_value = CredentialState.MISSING

    engines = MagicMock()
    engines.list_backend_names.return_value = ["claude_code", "opencode"]
    engines.list_credentials.return_value = [cred_present, cred_missing]

    svc = _make_service(agents=agents, execution=execution, engines=engines)

    with patch(
        "agentbox.core.service.diagnostics.load_settings",
        return_value=_mock_settings(tmp_path),
    ), patch(
        "agentbox.core.service.diagnostics.workspace_info",
    ):
        checks = svc.run_checks()

    details = {c.name: c.detail for c in checks}
    assert details.get("  claude_code") == "configured"
    assert details.get("  opencode") == "missing"


def test_run_checks_mcp_cache_exists(tmp_path) -> None:
    """MCP cache check reports number of cached JSON files when dir exists."""
    agents = MagicMock()
    agents.list_all_agents.return_value = []
    execution = MagicMock()
    execution.list_runs.return_value = []
    engines = MagicMock()
    engines.list_backend_names.return_value = []
    engines.list_credentials.return_value = []

    # Create two fake cache files
    cache_dir = tmp_path / "mcp_cache"
    cache_dir.mkdir()
    (cache_dir / "server_a.json").write_text("{}")
    (cache_dir / "server_b.json").write_text("{}")

    settings = MagicMock()
    settings.db_path = tmp_path / "agentbox.db"
    settings.mcp_cache_dir = cache_dir

    svc = _make_service(agents=agents, execution=execution, engines=engines)

    with patch(
        "agentbox.core.service.diagnostics.load_settings",
        return_value=settings,
    ), patch(
        "agentbox.core.service.diagnostics.workspace_info",
    ):
        checks = svc.run_checks()

    mcp_checks = [c for c in checks if c.name == "MCP cache"]
    assert len(mcp_checks) == 1
    assert mcp_checks[0].ok is True
    assert "2" in mcp_checks[0].detail
