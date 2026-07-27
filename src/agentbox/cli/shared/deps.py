"""CLI-layer shared singletons — mirrors ``api/deps.py`` factories.

CLI commands should NOT import from ``agentbox.api.deps`` per the
dependency-direction rule (CLI → API is a reverse dependency). Instead
they use these CLI-owned factory functions, which are functionally
identical to, but architecturally independent from, the API layer.

Each factory is ``@lru_cache`` so a typer callback context or scoped
command group can call it without recreating heavy objects.
"""

from __future__ import annotations

from functools import lru_cache
from agentbox.core.config import Settings, load_settings
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.mcp import McpRegistry

from agentbox.core.service.workspaces import WorkspaceService


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)


def _resolve_workspace_creds(ws_id: str) -> dict[str, str] | None:
    cs = CredentialService()
    if cs.list_workspace_credentials(ws_id):
        return cs.resolve_env_for_workspace(ws_id)
    return None


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    # Inject service-backed resolvers so core.execution never imports core.service.
    return RunExecutor(
        get_settings(),
        get_mcp_registry(),
        resolve_workspace_creds=_resolve_workspace_creds,
        project_mcp_servers=lambda: SystemService().get_project_mcp_servers(),
    )


# Service factories — each service is zero-argument and self-wiring.
from agentbox.core.service import (  # noqa: E402
    AgentService,
    CredentialService,
    DiagnosticsService,
    EngineService,
    ExecutionService,
    EvaluationService,
    SystemService,
)
from agentbox.core.service.resources import ResourceService  # noqa: E402
from agentbox.core.service.materialization_io import MaterializationService  # noqa: E402


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    return AgentService()


@lru_cache(maxsize=1)
def get_execution_service() -> ExecutionService:
    return ExecutionService()


@lru_cache(maxsize=1)
def get_engine_service() -> EngineService:
    return EngineService()


@lru_cache(maxsize=1)
def get_evaluation_service() -> EvaluationService:
    return EvaluationService()


@lru_cache(maxsize=1)
def get_system_service() -> SystemService:
    return SystemService()


@lru_cache(maxsize=1)
def get_resource_service() -> ResourceService:
    return ResourceService()


@lru_cache(maxsize=1)
def get_workspace_service() -> WorkspaceService:
    """Workspace-domain service. Cached — self-wires from settings."""
    return WorkspaceService()


def get_diagnostics_service() -> DiagnosticsService:
    """Diagnostics service — uncached, self-wiring."""
    return DiagnosticsService()


@lru_cache(maxsize=1)
def get_materialization_service() -> MaterializationService:
    """Materialization service — cached, self-wiring."""
    return MaterializationService()
