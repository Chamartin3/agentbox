"""Agents → Engines bridge.

The sole supported path for Runs and other consumers to resolve a backend
adapter by name. Wraps the plugin loader so the rest of the codebase never
imports ``core.agent.plugins`` directly. This makes the Engines carve-out
(planned) a renaming exercise on this single file.

Phase 2 of `workdir/modilarization/plans/AGENTS_PLAN.md`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.agents.plugins import (
    backend_load_failure as _backend_load_failure,
    backends as _backends,
    get_backend as _get_backend,
)

if TYPE_CHECKING:
    from agentbox.core.run.backends.base import BackendAdapter


def resolve_engine_by_name(name: str) -> type[BackendAdapter]:
    """Return the registered backend adapter class for ``name``.

    Raises ``KeyError`` if no plugin is registered for that name. Callers
    that want to know *why* a backend is missing should consult
    :func:`engine_load_failure`.
    """
    return _get_backend(name)


def list_engines() -> dict[str, type[BackendAdapter]]:
    """Return all registered engine adapters keyed by entry-point name."""
    return _backends()


def engine_load_failure(name: str) -> str | None:
    """Return why an engine plugin failed to load, or ``None``."""
    return _backend_load_failure(name)


__all__ = [
    "engine_load_failure",
    "list_engines",
    "resolve_engine_by_name",
]
