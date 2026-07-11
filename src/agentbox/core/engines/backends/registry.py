"""Plugin loader — discovers backends from entry points."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import TypeVar

from agentbox.core.engines.backends.base import BackendAdapter

T = TypeVar("T")

logger = logging.getLogger(__name__)

#: Per-group record of entry points that failed to load, keyed by ep.name →
#: short reason string ("ModuleNotFoundError: No module named 'foo'"). Lets
#: HTTP handlers report *why* a backend is missing instead of just "unknown".
_LOAD_FAILURES: dict[str, dict[str, str]] = {}


def _load_group(group: str, base: type[T]) -> dict[str, type[T]]:
    out: dict[str, type[T]] = {}
    failures: dict[str, str] = {}
    for ep in entry_points(group=group):
        try:
            cls = ep.load()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            failures[ep.name] = reason
            logger.warning(
                "agentbox: plugin %s:%s failed to load (%s)", group, ep.name, reason
            )
            continue
        if not (isinstance(cls, type) and issubclass(cls, base)):
            reason = f"not a {base.__name__} subclass"
            failures[ep.name] = reason
            logger.warning(
                "agentbox: plugin %s:%s failed to load (%s)", group, ep.name, reason
            )
            continue
        if ep.name in out:
            logger.warning(
                "agentbox: duplicate plugin name %r in %r; %s.%s overwritten by %s.%s",
                ep.name,
                group,
                out[ep.name].__module__,
                out[ep.name].__name__,
                cls.__module__,
                cls.__name__,
            )
        out[ep.name] = cls
    _LOAD_FAILURES[group] = failures
    return out


_BACKEND_CLASSES: dict[str, type[BackendAdapter]] | None = None


def backends() -> dict[str, type[BackendAdapter]]:
    global _BACKEND_CLASSES
    if _BACKEND_CLASSES is None:
        _BACKEND_CLASSES = _load_group("agentbox.backends", BackendAdapter)
    return _BACKEND_CLASSES or {}


def backend_load_failure(name: str) -> str | None:
    """Return why a backend entry point failed to load, or None if it loaded
    or was never registered. Use this to tell clients *why* a backend they
    asked for is unavailable instead of a bare "not found"."""
    backends()  # ensure loading has been attempted
    return _LOAD_FAILURES.get("agentbox.backends", {}).get(name)


def get_backend(name: str) -> type[BackendAdapter]:
    cls = backends().get(name)
    if cls is None:
        raise KeyError(f"no backend adapter registered for name={name!r}")
    return cls
