"""Lazy singletons for the MCP server.

Mirrors ``agentbox.api.deps`` but is independent so the MCP server can
run in its own process without importing the FastAPI app.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from agentbox.config import Settings, load_settings
from agentbox.core.service import SessionStore
from agentbox.core.service import ProjectManifest


class _NoopLoader:
    """Empty loader stub — see ``agentbox.api.deps._NoopLoader``."""

    def get(self, agent_id: str) -> Any:
        return None

    def load(self) -> ProjectManifest:
        return ProjectManifest()

    def get_workspace(self, name: str) -> Any:
        return None

    def list_workspaces(self) -> list:
        return []


@dataclass(frozen=True)
class Context:
    settings: Settings
    store: SessionStore
    loader: _NoopLoader


@lru_cache(maxsize=1)
def get_context() -> Context:
    settings = load_settings()
    store = SessionStore(settings.db_path)
    return Context(settings=settings, store=store, loader=_NoopLoader())
