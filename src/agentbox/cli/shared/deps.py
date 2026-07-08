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
from agentbox.core.db.database import Database  # ponytail: transitional — 113_04 routes DI through Services
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.workspaces.tooling.mcp import McpRegistry

from agentbox.core.service.workspaces.service import WorkspaceService


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database(get_settings().db_path)


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_db(), get_settings(), get_mcp_registry())


# ---------------------------------------------------------------------------
# Service factories — each service is zero-argument and self-wiring.
# EngineService is imported directly from its module rather than the facade
# because the facade defers the export due to a circular-import (plan 091).
# TODO(cli-arch): switch to ``from agentbox.core.service import EngineService``
#                 once that circular import is resolved.
# ---------------------------------------------------------------------------

from agentbox.core.service import (  # noqa: E402
    AgentService,
    ExecutionService,
    EvaluationService,
    SystemService,
)
from agentbox.core.service.engines.service import EngineService  # noqa: E402
from agentbox.core.service.resources.service import ResourceService  # noqa: E402


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
