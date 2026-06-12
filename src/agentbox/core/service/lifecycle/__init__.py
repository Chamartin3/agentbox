"""Application startup lifecycle.

Single entry point :func:`run_startup_tasks` that the FastAPI app and
any CLI launcher invoke during boot.
"""

from agentbox.core.service.lifecycle.report import StartupReport as StartupReport
from agentbox.core.service.lifecycle.startup import (
    ENV_IMPORT_ON_START as ENV_IMPORT_ON_START,
    ENV_MIGRATE_COMPOSITION as ENV_MIGRATE_COMPOSITION,
    ENV_SKIP_DEFAULT_PROFILES as ENV_SKIP_DEFAULT_PROFILES,
    ENV_SKIP_RESOURCE_IMPORT as ENV_SKIP_RESOURCE_IMPORT,
    boot_import_resources as boot_import_resources,
    discover_agent_tools as discover_agent_tools,
    dispatch_orphan_webhooks as dispatch_orphan_webhooks,
    import_on_start_sweep as import_on_start_sweep,
    reap_orphan_runs as reap_orphan_runs,
    run_startup_tasks as run_startup_tasks,
    seed_runner_profiles as seed_runner_profiles,
    sync_project_mcp_servers as sync_project_mcp_servers,
    sync_workspace_registry as sync_workspace_registry,
)

__all__ = [
    "StartupReport",
    "run_startup_tasks",
    "discover_agent_tools",
    "sync_project_mcp_servers",
    "import_on_start_sweep",
    "seed_runner_profiles",
    "boot_import_resources",
    "sync_workspace_registry",
    "reap_orphan_runs",
    "dispatch_orphan_webhooks",
    "ENV_IMPORT_ON_START",
    "ENV_SKIP_DEFAULT_PROFILES",
    "ENV_SKIP_RESOURCE_IMPORT",
    "ENV_MIGRATE_COMPOSITION",
]
