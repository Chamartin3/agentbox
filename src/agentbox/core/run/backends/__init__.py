"""Backend adapter registry — discover and select agent backends."""

from __future__ import annotations

from agentbox.core.agent.plugins import backends
from agentbox.core.agent.plugins import get_backend as _resolve_backend
from agentbox.core.run.backends.base import BackendAdapter, RenderedConfig


def get_backend(name: str) -> BackendAdapter:
    """Look up ``name`` in the ``agentbox.backends`` entry-point group,
    instantiate, and return the adapter."""
    return _resolve_backend(name)()


def list_backends() -> list[str]:
    return sorted(backends().keys())


__all__ = ["BackendAdapter", "RenderedConfig", "get_backend", "list_backends"]
