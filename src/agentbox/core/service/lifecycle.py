"""Application startup lifecycle.

Single entry point :func:`run_startup_tasks` that the FastAPI app and
any CLI launcher invoke during boot. Each named phase is independently
importable and testable; failures in one phase log and continue so a
single misbehaving subsystem cannot block the rest of the boot.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field, replace
from typing import Final

from agentbox.config import Settings
from agentbox.core.agents.composition.versioning.drift import startup_sweep
from agentbox.core.data import ProjectManifest, SessionStore
from agentbox.core.data.manifest import McpServerSpec
from agentbox.core.data.runners.seeds import seed_default_runner_profiles
from agentbox.core.resource.boot_import import (
    import_composition_references,
    import_repo_resources,
    sweep_workspace_skill_bindings,
)
from agentbox.core.resource.composition_to_bindings import (
    migrate_composition_to_bindings,
)
from agentbox.core.resource.legacy_migration import (
    migrate_shared_resources_to_repo,
)
from agentbox.core.run.execute.webhooks import schedule_webhook
from agentbox.core.service.agents import resolve_agent
from agentbox.core.tools import discover_tools
from agentbox.core.workspace.mcp.client import McpRegistry
from agentbox.core.workspace.mcp.client.registry import McpServerConfig

_log = logging.getLogger(__name__)

# Env-var feature flags. Single source of truth for boot-time gates.
ENV_IMPORT_ON_START: Final[str] = "AGENTBOX_IMPORT_ON_START"
ENV_SKIP_DEFAULT_PROFILES: Final[str] = "AGENTBOX_SKIP_DEFAULT_PROFILES"
ENV_SKIP_RESOURCE_IMPORT: Final[str] = "AGENTBOX_SKIP_RESOURCE_IMPORT"
ENV_MIGRATE_COMPOSITION: Final[str] = "AGENTBOX_MIGRATE_COMPOSITION"


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
        specs_models = store.get_project_mcp_servers()
    except Exception as exc:
        _log.exception("project mcp server lookup failed")
        return _error("sync_mcp_servers", exc)
    if not specs_models:
        return StartupReport()
    try:
        registry = McpRegistry(settings.mcp_cache_dir)
        specs: list[McpServerConfig] = [_to_mcp_config(s) for s in specs_models]
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
    if os.environ.get(ENV_IMPORT_ON_START) != "1":
        return StartupReport()
    if manifest is None or not manifest.agents:
        return StartupReport()
    try:
        project_root = settings.project_root
        shared_roots = {
            k: (project_root / v).resolve()
            for k, v in store.get_project_shared_assets().items()
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
    if os.environ.get(ENV_SKIP_DEFAULT_PROFILES):
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
    if os.environ.get(ENV_SKIP_RESOURCE_IMPORT):
        return StartupReport()

    out = _phase_import_repo(store, settings)
    out = _merge(out, _phase_legacy_migration(store))
    out = _merge(out, _phase_workspace_bindings(store, manifest))
    out = _merge(out, _phase_composition_refs(store, settings, manifest))
    if os.environ.get(ENV_MIGRATE_COMPOSITION):
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
        reaped = store.reap_orphan_runs()
    except Exception as exc:
        _log.exception("orphan run sweep failed")
        return _error("reap_orphan_runs", exc)
    if reaped:
        _log.warning("reaped %d orphaned 'running' run(s) on startup", reaped)
    return StartupReport(orphan_runs_reaped=reaped)


def dispatch_orphan_webhooks(store: SessionStore) -> StartupReport:
    """Fire webhooks for orphan-reaped runs whose post pipeline never ran.

    ``SessionStore`` reaps orphans synchronously inside ``__init__``,
    before the event loop exists, so the webhooks couldn't have been
    scheduled then. This phase runs once the loop is up.
    """
    try:
        pending = store.list_orphaned_unnotified_runs()
    except Exception as exc:
        _log.exception("orphan webhook lookup failed")
        return _error("dispatch_orphan_webhooks", exc)
    if not pending:
        return StartupReport()
    _log.warning("scheduling webhooks for %d orphan-reaped run(s)", len(pending))
    scheduled = 0
    for run in pending:
        try:
            agent = resolve_agent(run.agent_id, store=store)
            schedule_webhook(agent, run, store)
            scheduled += 1
        except Exception:
            _log.exception("orphan webhook dispatch failed for run %s", run.id)
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
    report = _merge(report, dispatch_orphan_webhooks(store))
    return report


# ---------------------------------------------------------------------------
# boot_import_resources sub-phases — kept private; only ``boot_import_resources``
# orders them. Splitting them out keeps cyclomatic complexity in check.
# ---------------------------------------------------------------------------


def _phase_import_repo(store: SessionStore, settings: Settings) -> StartupReport:
    try:
        summary = import_repo_resources(store, settings.project_root)
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


def _phase_legacy_migration(store: SessionStore) -> StartupReport:
    try:
        report = migrate_shared_resources_to_repo(store)
        summary = report.summary()
    except Exception as exc:
        _log.exception("legacy shared_resources sweep failed")
        return _error("migrate_shared_resources_to_repo", exc)
    if summary["migrated"] or summary["failed"]:
        _log.info("legacy shared_resources sweep: %s", summary)
    else:
        _log.debug("legacy shared_resources sweep: %s", summary)
    return StartupReport()


def _phase_workspace_bindings(
    store: SessionStore, manifest: ProjectManifest | None
) -> StartupReport:
    try:
        summary = sweep_workspace_skill_bindings(store, manifest)
    except Exception as exc:
        _log.exception("workspace skill binding sweep failed")
        return _error("sweep_workspace_skill_bindings", exc)
    if summary["bindings_added"]:
        _log.info(
            "boot-import workspace bindings: wired %d workspace(s), "
            "%d binding(s)",
            summary["workspaces_wired"],
            summary["bindings_added"],
        )
    return StartupReport(
        workspaces_wired=int(summary.get("workspaces_wired", 0)),
        workspace_bindings_added=int(summary.get("bindings_added", 0)),
    )


def _phase_composition_refs(
    store: SessionStore,
    settings: Settings,
    manifest: ProjectManifest | None,
) -> StartupReport:
    try:
        summary = import_composition_references(
            store, settings.project_root, manifest
        )
    except Exception as exc:
        _log.exception("composition refs import failed")
        return _error("import_composition_references", exc)
    if summary["bindings_added"]:
        _log.info(
            "boot-import composition refs: wired %d agent(s), "
            "%d resource(s), %d binding(s)",
            summary["agents_wired"],
            summary["resources_created"],
            summary["bindings_added"],
        )
    return StartupReport(
        composition_agents_wired=int(summary.get("agents_wired", 0)),
        composition_bindings_added=int(summary.get("bindings_added", 0)),
    )


def _phase_composition_migration(
    store: SessionStore, settings: Settings
) -> StartupReport:
    try:
        report = migrate_composition_to_bindings(
            store, project_root=settings.project_root
        )
        summary = report.summary()
    except Exception as exc:
        _log.exception("composition→bindings migration failed")
        return _error("migrate_composition_to_bindings", exc)
    if summary["bindings_created"] or summary["failed"]:
        _log.info("composition→bindings migration: %s", summary)
    else:
        _log.debug("composition→bindings migration: %s", summary)
    return StartupReport()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
