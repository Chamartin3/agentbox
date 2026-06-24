"""Singletons shared across FastAPI routes."""

from __future__ import annotations

from functools import lru_cache

from agentbox.core.config import Settings, load_settings
from agentbox.core.db import Database
from agentbox.core.service import AgentService, EvaluationService, ExecutionService, SessionStore
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.workspaces.mcp.client import McpRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    return SessionStore(get_settings().db_path)


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


# ── Stubs for services not yet migrated (plans 089–092) ──────────────────

def get_engine_service():
    """TODO: plan 091 — EngineService. Lazy import to avoid circular import."""
    from agentbox.core.service.engines.service import EngineService  # noqa: PLC0415
    return EngineService()


def get_resource_service():
    """TODO: plan 090 — ResourceService. Lazy import to avoid circular import."""
    from agentbox.core.service.resources.service import ResourceService  # noqa: PLC0415
    return ResourceService()


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_store(), get_settings(), get_mcp_registry(), db=get_db())


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)
