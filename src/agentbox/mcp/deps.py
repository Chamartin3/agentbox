"""Lazy singletons for the MCP server.

Mirrors ``agentbox.api.deps`` but is independent so the MCP server can
run in its own process without importing the FastAPI app.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from agentbox.core.config import Settings, load_settings
from agentbox.core.db import Database
from agentbox.core.service import (
    AgentService,
    ResourceService,
    SessionStore,
    WorkspaceService,
)


# ── Private helpers (internal — context.py constructs from these) ────────

@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def _get_store() -> SessionStore:
    return SessionStore(_get_settings().db_path)


@lru_cache(maxsize=1)
def _get_db() -> Database:
    return Database(_get_settings().db_path)


# ── Legacy context (kept temporarily for backward compat during migration) ──

@dataclass(frozen=True)
class _LegacyContext:
    settings: Settings
    store: SessionStore
    db: Database


@lru_cache(maxsize=1)
def _get_context() -> _LegacyContext:
    settings = _get_settings()
    store = _get_store()
    db = _get_db()
    return _LegacyContext(settings=settings, store=store, db=db)


# Public alias for backward compat during migration
get_context = _get_context
Context = _LegacyContext


# ── Service factories (kept temporarily for backward compat) ─────────────

def get_agent_service() -> AgentService:
    """Agent-domain service. Uncached — self-wires from settings and holds a
    path-cached Database, so a fresh instance per call stays correct."""
    return AgentService()


def get_resource_service() -> ResourceService:
    """Resource-domain service. Uncached — Database is lru_cache'd per path."""
    return ResourceService()


def get_workspace_service():
    """Workspace-domain service. Uncached — self-wires from settings."""
    return WorkspaceService()
