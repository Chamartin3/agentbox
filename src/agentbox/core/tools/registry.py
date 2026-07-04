from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

logger = logging.getLogger(__name__)


# ── ToolSpec + shared registry ────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolSpec:
    name: str  # canonical dotted name, e.g. "cv.score_bullet"
    description: str  # shown to the LLM
    capability: str  # grant key — defaults to name
    tags: tuple[str, ...]
    fn: Callable[..., Any]
    input_model: type  # pydantic BaseModel
    output_model: type  # pydantic BaseModel


# Process-wide registry: canonical name -> ToolSpec
_REGISTRY: dict[str, ToolSpec] = {}


class SharedToolRegistry:
    @staticmethod
    def register(spec: ToolSpec) -> None:
        if spec.name in _REGISTRY:
            raise ValueError(f"agent_tool {spec.name!r} already registered")
        _REGISTRY[spec.name] = spec

    @staticmethod
    def get(name: str) -> ToolSpec | None:
        return _REGISTRY.get(name)

    @staticmethod
    def all() -> list[ToolSpec]:
        return list(_REGISTRY.values())

    @staticmethod
    def clear() -> None:
        """Test helper — clears registry between test runs."""
        _REGISTRY.clear()


# ── @agent_tool decorator ────────────────────────────────────────────────────


def agent_tool(
    *,
    name: str,
    description: str,
    capability: str | None = None,
    tags: list[str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that registers a callable as a shared agent tool.

    The decorated function must have exactly one positional parameter
    typed as a pydantic BaseModel (input) and return a pydantic BaseModel
    (output). Both are required for the token backend's structured-call path.

    Usage:
        @agent_tool(name="cv.score_bullet", description="Score a resume bullet")
        def score_bullet(input: ScoreIn) -> ScoreOut: ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        if len(params) != 1:
            raise TypeError(
                f"@agent_tool {name!r}: function must take exactly one "
                f"pydantic BaseModel parameter, got {len(params)}"
            )
        input_model = params[0].annotation
        output_model = sig.return_annotation
        if (
            input_model is inspect.Parameter.empty
            or output_model is inspect.Parameter.empty
        ):
            raise TypeError(
                f"@agent_tool {name!r}: input and return type annotations are required"
            )
        spec = ToolSpec(
            name=name,
            description=description,
            capability=capability or name,
            tags=tuple(tags or []),
            fn=fn,
            input_model=input_model,
            output_model=output_model,
        )
        SharedToolRegistry.register(spec)
        setattr(fn, "_agent_tool_spec", spec)
        return fn

    return decorator


# ── Entry-point discovery ────────────────────────────────────────────────────

_DISCOVERED = False


def discover_tools(force: bool = False) -> None:
    """Import every entry point in the agentbox.agent_tools group.

    Best-effort: a broken entry point is logged and skipped.
    Idempotent — subsequent calls are no-ops unless force=True.
    """
    global _DISCOVERED
    if _DISCOVERED and not force:
        return
    eps = entry_points(group="agentbox.agent_tools")
    for ep in eps:
        try:
            ep.load()
            logger.debug("agent_tools: discovered %r from %r", ep.name, ep.value)
        except Exception:
            logger.exception(
                "agent_tools: failed to load entry point %r (%r) — skipping",
                ep.name,
                ep.value,
            )
    _DISCOVERED = True
