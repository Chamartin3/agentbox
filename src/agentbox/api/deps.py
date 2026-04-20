"""Singletons shared across FastAPI routes."""

from __future__ import annotations

from functools import lru_cache

from agentbox.config import SETTINGS, Settings
from agentbox.core.definitions import DefinitionLoader
from agentbox.core.executor import RunExecutor
from agentbox.core.session_store import SessionStore


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return SETTINGS


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    return SessionStore(get_settings().db_path)


@lru_cache(maxsize=1)
def get_loader() -> DefinitionLoader:
    return DefinitionLoader(get_settings().project_root)


@lru_cache(maxsize=1)
def get_executor() -> RunExecutor:
    return RunExecutor(get_store(), get_settings(), get_loader())
