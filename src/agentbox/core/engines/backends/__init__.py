"""Backend adapter registry — discover and select agent backends."""

from __future__ import annotations

from agentbox.core.engines.backends.registry import backends as _backends, get_backend as _get_backend_class
from agentbox.core.engines.contracts.base import BackendAdapter, RenderedConfig


def get_backend(name: str) -> BackendAdapter:
    """Look up ``name`` in the ``agentbox.backends`` entry-point group,
    instantiate, and return the adapter."""
    return _get_backend_class(name)()


def list_backends() -> list[str]:
    return sorted(_backends().keys())


__all__ = ["BackendAdapter", "RenderedConfig", "get_backend", "list_backends"]
