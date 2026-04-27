"""Singletons shared across FastAPI routes."""

from __future__ import annotations

from functools import lru_cache

from agentbox.config import Settings, load_settings
from agentbox.core.data import SessionStore
from agentbox.core.definitions import DefinitionLoader
from agentbox.core.executor import RunExecutor
from agentbox.core.mcp import McpRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    return SessionStore(get_settings().db_path)


@lru_cache(maxsize=1)
def get_loader() -> DefinitionLoader:
    settings = get_settings()
    return DefinitionLoader(
        settings.project_root,
        manifest_path=settings.manifest_path,
        agents_bundle_dir=settings.agents_bundle_dir,
    )


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_store(), get_settings(), get_loader(), get_mcp_registry())


@lru_cache(maxsize=1)
def get_mcp_registry() -> McpRegistry:
    settings = get_settings()
    return McpRegistry(settings.mcp_cache_dir)
