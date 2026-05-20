from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from agentbox.agent_tools.registry import SharedToolRegistry, ToolSpec


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
        params = [
            p for p in sig.parameters.values() if p.name != "self"
        ]
        if len(params) != 1:
            raise TypeError(
                f"@agent_tool {name!r}: function must take exactly one "
                f"pydantic BaseModel parameter, got {len(params)}"
            )
        input_model = params[0].annotation
        output_model = sig.return_annotation
        if input_model is inspect.Parameter.empty or output_model is inspect.Parameter.empty:
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
        fn._agent_tool_spec = spec  # type: ignore[attr-defined]
        return fn

    return decorator
