"""Base class for all core service objects.

Every ``XxxService`` inherits ``Service`` so they share one structure:
the ``Database`` dependency is resolved *internally* from settings — callers
construct services with no arguments (``AgentService()``), never passing a db.

``Database.__init__`` runs Alembic migrations on construction, so it must not
be rebuilt per service instance. ``_database()`` memoizes one Database per
db_path; unique paths (e.g. per-test tmp dirs) get their own instance.

ponytail: concrete base, not ``abc.ABC`` — services share no abstract
operation to enforce, only this db wiring. Add abstractmethods here if a
common operation ever emerges.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from agentbox.core.config import load_settings
from agentbox.core.db import Database


@lru_cache(maxsize=None)
def _database(db_path: str) -> Database:
    """Process-wide Database per db_path (migrations run once per path)."""
    return Database(Path(db_path))


class Service:
    """Shared base: resolves the Database dependency from settings."""

    def __init__(self) -> None:
        self._db = _database(str(load_settings().db_path))
