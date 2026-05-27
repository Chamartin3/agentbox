from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


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
