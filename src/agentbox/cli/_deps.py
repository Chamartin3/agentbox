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
from agentbox.core.db import Database
from agentbox.core.service import SessionStore
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


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_store(), get_settings(), get_mcp_registry(), db=get_db())
