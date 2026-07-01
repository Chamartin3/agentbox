"""Application startup lifecycle.

Single entry point :func:`run_startup_tasks` that the FastAPI app and
any CLI launcher invoke during boot. Each named phase is independently
importable and testable; failures in one phase log and continue so a
single misbehaving subsystem cannot block the rest of the boot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from agentbox.core.config import SETTINGS, Settings
from agentbox.core.agents.composition.drift import startup_sweep as _startup_sweep
from agentbox.core.data import ProjectManifest, RunRecord
from agentbox.core.db.database import Database
from agentbox.core.service.system.service import SystemService
from agentbox.core.db.engines.seeds import seed_default_runner_profiles
from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.service.agents import resolve_agent
from agentbox.core.service.execution.service import ExecutionService
from agentbox.core.tools import discover_tools
from agentbox.core.workspaces.mcp.client import McpRegistry
from agentbox.core.service.lifecycle._phases import (
    _phase_composition_migration,
    _phase_composition_refs,
    _phase_import_repo,
    _phase_legacy_migration,
    _phase_workspace_bindings,
)
from agentbox.core.service.lifecycle._utils import (
    _error,
    _merge,
    _swallow_task_exception,
    _to_mcp_config,
)
from agentbox.core.service.lifecycle.report import StartupReport

_log = logging.getLogger(__name__)

# Env-var feature flags. Single source of truth for boot-time gates.
ENV_IMPORT_ON_START: Final[str] = "AGENTBOX_IMPORT_ON_START"
ENV_SKIP_DEFAULT_PROFILES: Final[str] = "AGENTBOX_SKIP_DEFAULT_PROFILES"
ENV_SKIP_RESOURCE_IMPORT: Final[str] = "AGENTBOX_SKIP_RESOURCE_IMPORT"
ENV_MIGRATE_COMPOSITION: Final[str] = "AGENTBOX_MIGRATE_COMPOSITION"


def discover_agent_tools() -> StartupReport:
    """Populate the in-process agent_tools registry from entry points."""
    try:
        discover_tools()
    except Exception as exc:
        _log.exception("agent_tools discovery failed")
        return _error("discover_agent_tools", exc)
    return StartupReport(tools_discovered=True)


def sync_project_mcp_servers(
    db: Database, settings: Settings
) -> StartupReport:
    """Schedule async sync of any project-level MCP server specs."""
    try:
        specs_models = SystemService().get_project_mcp_servers()
    except Exception as exc:
        _log.exception("project mcp server lookup failed")
        return _error("sync_mcp_servers", exc)
    if not specs_models:
        return StartupReport()
    try:
        registry = McpRegistry(settings.mcp_cache_dir)
        specs = [_to_mcp_config(s) for s in specs_models]
        task = asyncio.ensure_future(registry.sync_servers(specs))
        task.add_done_callback(_swallow_task_exception)
    except Exception as exc:
        _log.exception("mcp registry sync scheduling failed")
        return _error("sync_mcp_servers", exc)
    return StartupReport(mcp_servers_synced=len(specs_models))


def import_on_start_sweep(
    manifest: ProjectManifest | None,
    db: Database,
    settings: Settings,
) -> StartupReport:
    """Filesystem → DB import for agent versions. Opt-in via env flag."""
    if not SETTINGS.import_on_start:
        return StartupReport()
    if manifest is None or not manifest.agents:
        return StartupReport()
    try:
        project_root = settings.project_root
        shared_roots = {
            k: (project_root / v).resolve()
            for k, v in SystemService().get_project_shared_assets().items()
        }
        _startup_sweep(
            manifest.agents,
            db.agent_versions,
            db.prompt_versions,
            db.runner_profiles,
            project_root=project_root,
            shared_roots=shared_roots,
        )
    except Exception as exc:
        _log.exception("startup drift sweep failed")
        return _error("import_on_start_sweep", exc)
    return StartupReport(drift_sweep_ran=True)


def seed_runner_profiles(db: Database) -> StartupReport:
    """Idempotent seed of the default runner profiles."""
    if SETTINGS.skip_default_profiles:
        return StartupReport()
    try:
        created = seed_default_runner_profiles()
    except Exception as exc:
        _log.exception("default runner profile seed failed")
        return _error("seed_runner_profiles", exc)
    if created:
        _log.info("seeded %d default runner profile(s)", created)
    return StartupReport(runner_profiles_seeded=created)


def boot_import_resources(
    db: Database,
    settings: Settings,
    manifest: ProjectManifest | None,
) -> StartupReport:
    """Populate the central resource repository from on-disk manifest layout."""
    if SETTINGS.skip_resource_import:
        return StartupReport()

    out = _phase_import_repo(db, settings)
    out = _merge(out, _phase_legacy_migration(db))
    out = _merge(out, _phase_workspace_bindings(db, manifest))
    out = _merge(out, _phase_composition_refs(db, settings, manifest))
    if SETTINGS.migrate_composition:
        out = _merge(out, _phase_composition_migration(db, settings))
    return out


def sync_workspace_registry(
    db: Database, manifest: ProjectManifest | None
) -> StartupReport:
    """Prune phantom workspace rows that no real subsystem references."""
    try:
        from agentbox.core.service.workspaces.service import WorkspaceService  # noqa: PLC0415
        keep: set[str] = {"default"}
        if manifest is not None:
            keep |= {a.workspace or "default" for a in manifest.agents}
        pruned = WorkspaceService().prune_phantoms(keep=keep)
    except Exception as exc:
        _log.exception("workspaces registry sync failed")
        return _error("sync_workspace_registry", exc)
    if pruned:
        _log.info(
            "pruned %d phantom workspace registry rows: %s",
            len(pruned),
            sorted(pruned),
        )
    return StartupReport(workspaces_pruned=len(pruned))


def reap_orphan_runs(db: Database) -> StartupReport:
    """Mark any pre-existing 'running' rows as orphaned."""
    try:
        reaped = ExecutionService().reap_orphan_runs()
    except Exception as exc:
        _log.exception("orphan run sweep failed")
        return _error("reap_orphan_runs", exc)
    if reaped:
        _log.warning("reaped %d orphaned 'running' run(s) on startup", reaped)
    return StartupReport(orphan_runs_reaped=reaped)


def dispatch_orphan_webhooks(
    db: Database, settings: Settings
) -> StartupReport:
    """Fire dispatch channels for orphan-reaped runs whose post pipeline never ran."""
    try:
        svc = ExecutionService()
        pending_raw = svc.list_orphaned_unnotified_runs()
        pending = [RunRecord(**r) for r in pending_raw] if pending_raw else []
    except Exception as exc:
        _log.exception("orphan dispatch lookup failed")
        return _error("dispatch_orphan_webhooks", exc)
    if not pending:
        return StartupReport()
    _log.warning("scheduling dispatches for %d orphan-reaped run(s)", len(pending))
    scheduled = 0
    for run in pending:
        try:
            agent = resolve_agent(run.agent_id, agent_defs=db.agent_defs)
            dispatch_completion(
                run=run,
                agent=agent,
                store=ExecutionService(),
                settings=settings,
            )
            scheduled += 1
        except Exception:
            _log.exception("orphan dispatch failed for run %s", run.id)
    return StartupReport(webhooks_scheduled=scheduled)


def run_startup_tasks(
    db: Database,
    settings: Settings,
    manifest: ProjectManifest | None,
) -> StartupReport:
    """Run every boot-time phase in canonical order."""
    settings.check_runtime_sources()
    report = StartupReport()
    report = _merge(report, discover_agent_tools())
    report = _merge(report, sync_project_mcp_servers(db, settings))
    report = _merge(report, import_on_start_sweep(manifest, db, settings))
    report = _merge(report, seed_runner_profiles(db))
    report = _merge(report, boot_import_resources(db, settings, manifest))
    report = _merge(report, sync_workspace_registry(db, manifest))
    report = _merge(report, reap_orphan_runs(db))
    report = _merge(report, dispatch_orphan_webhooks(db, settings))
    return report
