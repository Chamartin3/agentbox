"""Singletons shared across FastAPI routes."""

from __future__ import annotations

from functools import lru_cache

from agentbox.api.context import APIContext
from agentbox.core.config import Settings, load_settings
from agentbox.core.db.database import Database  # ponytail: transitional — 113_04 routes DI through Services
from agentbox.core.service import (
    AgentService,
    EngineService,
    EvaluationService,
    ExecutionService,
    ResourceService,
    SystemService,
    WorkspaceService,
)
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.mcp.client import McpRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_db() -> Database:
    return Database(get_settings().db_path)


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


# ── Stubs for services not yet migrated (plans 089–092) ──────────────────

def get_engine_service() -> EngineService:
    """TODO: plan 091 — EngineService. Lazy import to avoid circular import."""
    from agentbox.core.service.engines.service import EngineService  # noqa: PLC0415
    return EngineService()


def get_resource_service() -> ResourceService:
    """Resource-domain service. Uncached — self-wires from settings and is cheap."""
    return ResourceService()


def get_workspace_service() -> WorkspaceService:
    """Workspace-domain service. Uncached — self-wires from settings."""
    from agentbox.core.service.workspaces.service import WorkspaceService  # noqa: PLC0415
    return WorkspaceService()


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_db(), get_settings(), get_mcp_registry())


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)


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
    )
