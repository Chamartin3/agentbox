"""Singletons shared across FastAPI routes."""

from __future__ import annotations

from functools import lru_cache

from agentbox.api.context import APIContext
from agentbox.core.config import Settings, load_settings
from agentbox.core.service import (
    AgentService,
    CredentialService,
    EngineService,
    EvaluationService,
    ExecutionService,
    ResourceService,
    SystemService,
    WorkspaceService,
)
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.workspaces.tooling.mcp import McpRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def get_agent_service() -> AgentService:
    """Agent-domain service. Uncached: it self-wires from settings and is
    cheap (holds a path-cached Database), so a fresh instance per call stays
    correct under per-test AGENTBOX_DATA_DIR overrides."""
    return AgentService()


def get_execution_service() -> ExecutionService:
    """Execution-domain service. Uncached — self-wires from settings and is
    cheap (holds a path-cached Database)."""
    return ExecutionService()


def get_evaluation_service() -> EvaluationService:
    """Evaluation/analytics service. Uncached — self-wires from settings."""
    return EvaluationService()


def get_system_service() -> SystemService:
    """System/config service. Uncached — self-wires from settings."""
    return SystemService()


def get_engine_service() -> EngineService:
    """Engine-domain service. Uncached — self-wires from settings."""
    return EngineService()


def get_resource_service() -> ResourceService:
    """Resource-domain service. Uncached — self-wires from settings and is cheap."""
    return ResourceService()


def get_workspace_service() -> WorkspaceService:
    """Workspace-domain service. Uncached — self-wires from settings."""
    return WorkspaceService()


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_settings(), get_mcp_registry())


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    registry = McpRegistry(settings.mcp_cache_dir)
    registry.hydrate_from_cache()
    return registry


# ── API context — the single Depends for all routes ─────────────────────

def get_api_context() -> APIContext:
    """Build and return the ``APIContext`` carrying all seven service objects.

    Uncached: service constructors are cheap and self-wire from settings,
    so a fresh instance per request stays correct under per-test
    ``AGENTBOX_DATA_DIR`` overrides.
    """
    return APIContext(
        agents=AgentService(),
        workspaces=WorkspaceService(),
        resources=ResourceService(),
        execution=ExecutionService(),
        engines=EngineService(),
        evaluation=EvaluationService(),
        system=SystemService(),
        credentials=CredentialService(),
    )
