"""Backend adapter registry — discover and select agent backends."""

from __future__ import annotations

from agentbox.core.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.plugins import backends


def get_backend(name: str) -> BackendAdapter:
    """Look up ``name`` in the ``agentbox.backends`` entry-point group
    (falling back to ``agentbox.runners`` for backward compat), instantiate,
    and return the adapter."""
    from agentbox.core.plugins import get_backend as _resolve

    return _resolve(name)()


def list_backends() -> list[str]:
    return sorted(backends().keys())


__all__ = ["BackendAdapter", "RenderedConfig", "get_backend", "list_backends"]
