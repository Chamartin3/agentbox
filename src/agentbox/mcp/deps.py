"""Lazy singletons for the MCP server.

Mirrors ``agentbox.api.deps`` but is independent so the MCP server can
run in its own process without importing the FastAPI app.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from agentbox.core.config import Settings, load_settings
from agentbox.core.db import Database
from agentbox.core.service import AgentService, SessionStore


@dataclass(frozen=True)
class Context:
    settings: Settings
    store: SessionStore
    db: Database


@lru_cache(maxsize=1)
def get_context() -> Context:
    settings = load_settings()
    store = SessionStore(settings.db_path)
    db = Database(settings.db_path)
    return Context(settings=settings, store=store, db=db)


def get_agent_service() -> AgentService:
    """Agent-domain service. Uncached — self-wires from settings and holds a
    path-cached Database, so a fresh instance per call stays correct."""
    return AgentService()
