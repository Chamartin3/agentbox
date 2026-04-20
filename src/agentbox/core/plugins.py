"""Plugin loader — discovers runners/guardrails/adapters from entrypoints."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TypeVar

from agentbox.core.guardrails.base import Guardrail
from agentbox.core.runners.base import Runner

T = TypeVar("T")


def _load_group(group: str) -> dict[str, type]:
    out: dict[str, type] = {}
    for ep in entry_points(group=group):
        try:
            cls = ep.load()
        except Exception as exc:  # noqa: BLE001 - intentionally permissive
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


_RUNNER_CLASSES: dict[str, type[Runner]] | None = None
_GUARDRAIL_CLASSES: dict[str, type[Guardrail]] | None = None


def runners() -> dict[str, type[Runner]]:
    global _RUNNER_CLASSES
    if _RUNNER_CLASSES is None:
        _RUNNER_CLASSES = _load_group("agentbox.runners")  # type: ignore[assignment]
    return _RUNNER_CLASSES or {}


def guardrails() -> dict[str, type[Guardrail]]:
    global _GUARDRAIL_CLASSES
    if _GUARDRAIL_CLASSES is None:
        _GUARDRAIL_CLASSES = _load_group("agentbox.guardrails")  # type: ignore[assignment]
    return _GUARDRAIL_CLASSES or {}


def get_runner(kind: str) -> type[Runner]:
    cls = runners().get(kind)
    if cls is None:
        raise KeyError(f"no runner plugin registered for kind={kind!r}")
    return cls


def get_guardrail(name: str) -> type[Guardrail]:
    cls = guardrails().get(name)
    if cls is None:
        raise KeyError(f"no guardrail plugin registered for name={name!r}")
    return cls
