"""Plugin loader — discovers backends/guardrails from entry points."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING, TypeVar

from agentbox.core.guardrails.base import Guardrail

if TYPE_CHECKING:
    from agentbox.core.backends.base import BackendAdapter

T = TypeVar("T")


def _load_group(group: str) -> dict[str, type]:
    out: dict[str, type] = {}
    for ep in entry_points(group=group):
        try:
            cls = ep.load()
        except Exception as exc:
            print(f"agentbox: failed to load {group}:{ep.name}: {exc}")
            continue
        if ep.name in out:
            print(
                f"agentbox: WARNING — duplicate plugin name {ep.name!r} in {group!r}; "
                f"{out[ep.name].__module__}.{out[ep.name].__name__} overwritten by "
                f"{cls.__module__}.{cls.__name__}"
            )
        out[ep.name] = cls
    return out


_GUARDRAIL_CLASSES: dict[str, type[Guardrail]] | None = None
_BACKEND_CLASSES: dict[str, type[BackendAdapter]] | None = None


def guardrails() -> dict[str, type[Guardrail]]:
    global _GUARDRAIL_CLASSES
    if _GUARDRAIL_CLASSES is None:
        _GUARDRAIL_CLASSES = _load_group("agentbox.guardrails")  # type: ignore[assignment]
    return _GUARDRAIL_CLASSES or {}


def backends() -> dict[str, type[BackendAdapter]]:
    global _BACKEND_CLASSES
    if _BACKEND_CLASSES is None:
        _BACKEND_CLASSES = _load_group("agentbox.backends")  # type: ignore[assignment]
    return _BACKEND_CLASSES or {}


def get_backend(name: str) -> type[BackendAdapter]:
    cls = backends().get(name)
    if cls is None:
        raise KeyError(f"no backend adapter registered for name={name!r}")
    return cls


def get_guardrail(name: str) -> type[Guardrail]:
    cls = guardrails().get(name)
    if cls is None:
        raise KeyError(f"no guardrail plugin registered for name={name!r}")
    return cls
