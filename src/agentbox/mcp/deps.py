"""Lazy singletons for the MCP server.

Mirrors ``agentbox.api.deps`` but is independent so the MCP server can
run in its own process without importing the FastAPI app.
"""

from __future__ import annotations

from functools import lru_cache

from agentbox.core.config import Settings, load_settings


# ── Private helpers (internal — context.py constructs from these) ────────

@lru_cache(maxsize=1)
def _get_settings() -> Settings:
    return load_settings()
