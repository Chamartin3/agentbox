"""StartupReport dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field


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
