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
from agentbox.core.agents.composition.drift import startup_sweep
from agentbox.core.db import ProjectManifest, RunRecord, SessionStore
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
    store: SessionStore, settings: Settings
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
    store: SessionStore,
    settings: Settings,
) -> StartupReport:
    """Filesystem → DB import for agent versions. Opt-in via env flag.

    Without ``AGENTBOX_IMPORT_ON_START=1`` the manifest is read-only at
    boot, so files cannot silently overwrite DB state.
    """
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
        startup_sweep(
            manifest.agents,
            store,
            project_root=project_root,
            shared_roots=shared_roots,
        )
    except Exception as exc:
        _log.exception("startup drift sweep failed")
        return _error("import_on_start_sweep", exc)
    return StartupReport(drift_sweep_ran=True)


def seed_runner_profiles(store: SessionStore) -> StartupReport:
    """Idempotent seed of the default runner profiles."""
    if SETTINGS.skip_default_profiles:
        return StartupReport()
    try:
        created = seed_default_runner_profiles(store)
    except Exception as exc:
        _log.exception("default runner profile seed failed")
        return _error("seed_runner_profiles", exc)
    if created:
        _log.info("seeded %d default runner profile(s)", created)
    return StartupReport(runner_profiles_seeded=created)


def boot_import_resources(
    store: SessionStore,
    settings: Settings,
    manifest: ProjectManifest | None,
) -> StartupReport:
    """Populate the central resource repository from on-disk manifest layout.

    Runs four idempotent sub-steps: repo import, legacy migration,
    workspace skill bindings, composition refs. Optionally runs the
    composition→bindings migration when its rollout flag is set.
    """
    if SETTINGS.skip_resource_import:
        return StartupReport()

    out = _phase_import_repo(store, settings)
    out = _merge(out, _phase_legacy_migration(store))
    out = _merge(out, _phase_workspace_bindings(store, manifest))
    out = _merge(out, _phase_composition_refs(store, settings, manifest))
    if SETTINGS.migrate_composition:
        out = _merge(out, _phase_composition_migration(store, settings))
    return out


def sync_workspace_registry(
    store: SessionStore, manifest: ProjectManifest | None
) -> StartupReport:
    """Prune phantom workspace rows that no real subsystem references."""
    try:
        keep: set[str] = {"default"}
        if manifest is not None:
            keep |= {a.workspace or "default" for a in manifest.agents}
        pruned = store.prune_phantom_workspaces(keep=keep)
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


def reap_orphan_runs(store: SessionStore) -> StartupReport:
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
    store: SessionStore, settings: Settings
) -> StartupReport:
    """Fire dispatch channels for orphan-reaped runs whose post pipeline never ran.

    ``SessionStore`` reaps orphans synchronously inside ``__init__``,
    before the event loop exists, so the dispatches couldn't have been
    scheduled then. This phase runs once the loop is up.
    """
    try:
        svc = ExecutionService()
        pending_raw = svc.list_orphaned_unnotified_runs()
        # Convert dicts back to RunRecord-like objects for downstream use
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
            agent = resolve_agent(run.agent_id, store=store)
            dispatch_completion(
                run=run,
                agent=agent,
                svc=ExecutionService(),
                settings=settings,
            )
            scheduled += 1
        except Exception:
            _log.exception("orphan dispatch failed for run %s", run.id)
    return StartupReport(webhooks_scheduled=scheduled)


def run_startup_tasks(
    store: SessionStore,
    settings: Settings,
    manifest: ProjectManifest | None,
) -> StartupReport:
    """Run every boot-time phase in canonical order.

    Each phase is best-effort: a failure logs and is recorded in
    :attr:`StartupReport.errors`, but never aborts the sequence.
    Migration ordering is preserved exactly from the legacy
    ``api.app._on_startup`` implementation.
    """
    settings.check_runtime_sources(store)
    report = StartupReport()
    report = _merge(report, discover_agent_tools())
    report = _merge(report, sync_project_mcp_servers(store, settings))
    report = _merge(report, import_on_start_sweep(manifest, store, settings))
    report = _merge(report, seed_runner_profiles(store))
    report = _merge(report, boot_import_resources(store, settings, manifest))
    report = _merge(report, sync_workspace_registry(store, manifest))
    report = _merge(report, reap_orphan_runs(store))
    report = _merge(report, dispatch_orphan_webhooks(store, settings))
    return report
