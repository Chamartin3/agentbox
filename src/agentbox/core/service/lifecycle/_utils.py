"""Internal utilities for the lifecycle module."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from agentbox.core.db.workspaces.manifest import McpServerSpec
from agentbox.core.service.lifecycle.report import StartupReport
from agentbox.core.workspaces.mcp.client.registry import McpServerConfig

_log = logging.getLogger(__name__)


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
