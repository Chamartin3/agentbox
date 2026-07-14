"""Application startup lifecycle.

Single entry point :func:`run_startup_tasks` that the FastAPI app and
any CLI launcher invoke during boot. Each named phase is independently
importable and testable; failures in one phase log and continue so a
single misbehaving subsystem cannot block the rest of the boot.

Not a domain service — a module of startup-orchestration functions plus
the ``StartupReport`` value type. (Consolidated from the former
lifecycle/ package: report + _utils + _phases + startup.)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import Any, Final

from agentbox.core.config import SETTINGS, Settings
from agentbox.core.data import RunRecord
from agentbox.core.data.manifests.workspaces import McpServerSpec
from agentbox.core.db.database import Database
from agentbox.core.db.seeds.engines import seed_default_runner_profiles
from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.resources.boot import import_repo_resources
from agentbox.core.service.execution import ExecutionService
from agentbox.core.service.system import SystemService
from agentbox.core.service.workspaces import WorkspaceService
from agentbox.core.tools import discover_tools
from agentbox.core.workspaces.tooling.mcp import McpRegistry
from agentbox.core.workspaces.tooling.mcp.registry import McpServerConfig

_log = logging.getLogger(__name__)

# Env-var feature flags. Single source of truth for boot-time gates.
ENV_IMPORT_ON_START: Final[str] = "AGENTBOX_IMPORT_ON_START"
ENV_SKIP_DEFAULT_PROFILES: Final[str] = "AGENTBOX_SKIP_DEFAULT_PROFILES"
ENV_SKIP_RESOURCE_IMPORT: Final[str] = "AGENTBOX_SKIP_RESOURCE_IMPORT"


@dataclass(frozen=True)
class StartupReport:
    """Outcome of one :func:`run_startup_tasks` invocation.

    Values are zero / ``False`` when a phase was skipped or did no work.
    ``errors`` collects readable per-phase failure messages; the API
    can log a single summary line at the end of boot.
    """

    tools_discovered: bool = False
    mcp_servers_synced: int = 0
    drift_sweep_ran: bool = False
    runner_profiles_seeded: int = 0
    resources_created: int = 0
    resources_updated: int = 0
    workspaces_wired: int = 0
    workspace_bindings_added: int = 0
    composition_agents_wired: int = 0
    composition_bindings_added: int = 0
    workspaces_pruned: int = 0
    orphan_runs_reaped: int = 0
    webhooks_scheduled: int = 0
    errors: list[str] = field(default_factory=list)


# ── internal helpers ───────────────────────────────────────────────────────


def _error(phase: str, exc: BaseException) -> StartupReport:
    """Build a StartupReport carrying a single error message."""
    return StartupReport(errors=[f"{phase}: {exc}"])


def _merge(base: StartupReport, delta: StartupReport) -> StartupReport:
    """Fold a phase's delta into the cumulative report.

    Boolean flags OR, counts sum, errors concatenate.
    """
    return replace(
        base,
        tools_discovered=base.tools_discovered or delta.tools_discovered,
        mcp_servers_synced=base.mcp_servers_synced + delta.mcp_servers_synced,
        drift_sweep_ran=base.drift_sweep_ran or delta.drift_sweep_ran,
        runner_profiles_seeded=base.runner_profiles_seeded
        + delta.runner_profiles_seeded,
        resources_created=base.resources_created + delta.resources_created,
        resources_updated=base.resources_updated + delta.resources_updated,
        workspaces_wired=base.workspaces_wired + delta.workspaces_wired,
        workspace_bindings_added=base.workspace_bindings_added
        + delta.workspace_bindings_added,
        composition_agents_wired=base.composition_agents_wired
        + delta.composition_agents_wired,
        composition_bindings_added=base.composition_bindings_added
        + delta.composition_bindings_added,
        workspaces_pruned=base.workspaces_pruned + delta.workspaces_pruned,
        orphan_runs_reaped=base.orphan_runs_reaped + delta.orphan_runs_reaped,
        webhooks_scheduled=base.webhooks_scheduled + delta.webhooks_scheduled,
        errors=[*base.errors, *delta.errors],
    )


def _swallow_task_exception(task: asyncio.Task[None]) -> None:
    """Background-task done callback that consumes the exception if any."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _log.warning("mcp sync background task failed: %s", exc)


def _to_mcp_config(spec: McpServerSpec) -> McpServerConfig:
    """Convert an ``McpServerSpec`` (Pydantic) to the ``McpServerConfig``
    TypedDict shape that ``McpRegistry.sync_servers`` consumes.
    """
    out: McpServerConfig = {
        "name": spec.name,
        "transport": spec.transport,
        "cache_ttl": spec.cache_ttl,
    }
    if spec.url is not None:
        out["url"] = spec.url
    if spec.command is not None:
        out["command"] = list(spec.command)
    return out


def _phase_import_repo(db: Any, settings: Settings) -> StartupReport:
    try:
        summary = import_repo_resources(
            db.resources, db.resource_versions, settings.project_root
        )
    except Exception as exc:
        _log.exception("repo-resource boot import failed")
        return _error("import_repo_resources", exc)
    if summary["created"] or summary["updated"]:
        _log.info(
            "boot-import repo_resources: created=%d updated=%d "
            "skipped=%d failed=%d",
            summary["created"],
            summary["updated"],
            summary["skipped"],
            summary["failed"],
        )
    return StartupReport(
        resources_created=int(summary.get("created", 0)),
        resources_updated=int(summary.get("updated", 0)),
    )


# ── boot phases ────────────────────────────────────────────────────────────


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
) -> StartupReport:
    """Populate the central resource repository from on-disk layout."""
    if SETTINGS.skip_resource_import:
        return StartupReport()

    return _phase_import_repo(db, settings)


def sync_workspace_registry(db: Database) -> StartupReport:
    """Prune phantom workspace rows that no real subsystem references."""
    try:
        pruned = WorkspaceService().prune_phantoms(keep={"default"})
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
            agent = db.agent_defs.get(run.agent_id)
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
    manifest: object = None,
) -> StartupReport:
    """Run every boot-time phase in canonical order.

    The ``manifest`` parameter is accepted for backward compatibility but
    ignored — the DB is the sole source of truth.
    """
    report = StartupReport()
    report = _merge(report, discover_agent_tools())
    report = _merge(report, sync_project_mcp_servers(db, settings))
    report = _merge(report, seed_runner_profiles(db))
    report = _merge(report, boot_import_resources(db, settings))
    report = _merge(report, sync_workspace_registry(db))
    report = _merge(report, reap_orphan_runs(db))
    report = _merge(report, dispatch_orphan_webhooks(db, settings))
    return report
