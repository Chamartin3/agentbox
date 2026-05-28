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
from typing import Any

from agentbox.config import Settings, load_settings
from agentbox.core.data import ProjectManifest, SessionStore
from agentbox.core.run.executor import RunExecutor
from agentbox.core.workspace.mcp.client import McpRegistry


class _NoopLoader:
    """Empty loader stub.

    The disk manifest loader is deprecated; the DB is the source of truth.
    This stub keeps the existing ``get_loader()`` call surface alive while
    we migrate call sites to talk to the store directly. All accessors
    return ``None`` / empty, matching "no manifest is available".
    """

    def get(self, agent_id: str) -> Any:
        return None

    def load(self) -> ProjectManifest:
        return ProjectManifest()

    def get_workspace(self, name: str) -> Any:
        return None

    def list_workspaces(self) -> list:
        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    return SessionStore(get_settings().db_path)


@lru_cache(maxsize=1)
def get_loader() -> _NoopLoader:
    return _NoopLoader()


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_store(), get_settings(), get_mcp_registry())
