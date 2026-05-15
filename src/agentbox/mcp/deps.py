"""Lazy singletons for the MCP server.

Mirrors ``agentbox.api.deps`` but is independent so the MCP server can
run in its own process without importing the FastAPI app.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from agentbox.config import Settings, load_settings
from agentbox.core.data import SessionStore
from agentbox.core.deprecated.definitions import DefinitionLoader


@dataclass(frozen=True)
class Context:
    settings: Settings
    store: SessionStore
    loader: DefinitionLoader


@lru_cache(maxsize=1)
def get_context() -> Context:
    settings = load_settings()
    store = SessionStore(settings.db_path)
    loader = DefinitionLoader(
        settings.project_root,
        manifest_path=settings.manifest_path,
        agents_bundle_dir=settings.agents_bundle_dir,
    )
    return Context(settings=settings, store=store, loader=loader)
