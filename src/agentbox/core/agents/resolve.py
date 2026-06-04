"""Agents → Engines bridge.

The sole supported path for Runs, MCP, and CLI callers to resolve a backend
adapter for an agent. Wraps the plugin loader so nothing else imports
``core.agents.plugins`` or ``core.engines.backends.*`` concrete classes
directly.
"""

from agentbox.core.engines.backends.registry import (
    backend_load_failure as _backend_load_failure,
    backends as _backends,
    get_backend as _get_backend,
)
from agentbox.core.engines.backends.base import BackendAdapter


def resolve_engine_by_name(name: str) -> type[BackendAdapter]:
    """Return the registered backend adapter class for ``name``."""
    return _get_backend(name)


def resolve_engine(name: str) -> BackendAdapter:
    """Return an instantiated backend adapter for ``name``.

    Raises ``KeyError`` if no plugin is registered for that name.
    """
    cls = _get_backend(name)
    return cls()


def list_engines() -> dict[str, type[BackendAdapter]]:
    """Return all registered engine adapters keyed by entry-point name."""
    return _backends()


def engine_load_failure(name: str) -> str | None:
    """Return why an engine plugin failed to load, or ``None``."""
    return _backend_load_failure(name)


__all__ = [
    "engine_load_failure",
    "list_engines",
    "resolve_engine",
    "resolve_engine_by_name",
]
