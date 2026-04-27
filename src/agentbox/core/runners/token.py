"""Token runner — runs a pydantic-ai ``Agent`` in-process with a single LLM call.

This is a thin wrapper around ``pydantic_ai.Agent``:

- ``system_prompt`` comes from ``req.agent.load_prompt`` (or the composed
  system prompt when the agent uses ``[composition]``).
- The user message comes from ``req.input``, which must be a JSON object
  ``{"user_message": str, "variables": dict}``. ``variables`` is exposed
  to the system prompt for Jinja-style templating by upstream composition
  (the runner itself just passes ``user_message`` to the Agent).
- Optional ``deps`` are built by a dotted-path callable declared on the
  ``RunnerSpec.deps_factory`` field, e.g.
  ``apps.cvman.agentbox_deps:build_deps``. The callable receives no
  arguments and its return value is passed to ``Agent.run_sync(... , deps=...)``.
- Model is taken from ``RunnerSpec.model``; falls back to pydantic-ai's
  default.

Output: the result's ``output`` is yielded as a ``TextEvent``. Token usage
is yielded as a ``UsageEvent`` when available. The run always terminates
with a ``DoneEvent``.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.runners.base import Runner, RunRequest


class TokenRunner(Runner):
    kind = "token"

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        spec = req.agent.runner

        try:
            from pydantic_ai import Agent
        except ImportError as exc:
            yield DoneEvent(
                run_id=req.run_id,
                ok=False,
                error=f"pydantic-ai is required for token runner: {exc}",
            )
            return

        system_prompt = req.agent.load_prompt(req.project_root)
        user_message, _variables = _parse_input(req.input)
        if user_message is None:
            yield DoneEvent(
                run_id=req.run_id,
                ok=False,
                error=(
                    "token runner input must be a JSON object with a "
                    "'user_message' string (and optional 'variables' dict)"
                ),
            )
            return

        deps = None
        if spec.deps_factory:
            try:
                deps = _build_deps(spec.deps_factory)
            except Exception as exc:
                yield DoneEvent(
                    run_id=req.run_id,
                    ok=False,
                    error=f"deps_factory error: {exc}",
                )
                return

        model = spec.model or os.environ.get("AGENTBOX_DEFAULT_MODEL")

        yield LogEvent(
            run_id=req.run_id,
            message=(
                f"[token] model={model or '<default>'} "
                f"deps_factory={spec.deps_factory or '<none>'}"
            ),
        )

        try:
            agent = Agent(model=model, system_prompt=system_prompt)
        except Exception as exc:
            yield DoneEvent(
                run_id=req.run_id,
                ok=False,
                error=f"agent construction error: {exc}",
            )
            return

        start = time.monotonic()
        try:
            if deps is None:
                result = agent.run_sync(user_message)
            else:
                result = agent.run_sync(user_message, deps=deps)
        except Exception as exc:
            yield DoneEvent(
                run_id=req.run_id,
                ok=False,
                error=f"agent execution error: {exc}",
            )
            return
        _elapsed = time.monotonic() - start

        output_text = _serialize_output(result)
        yield TextEvent(run_id=req.run_id, text=output_text)

        usage = _extract_usage(result)
        if usage is not None:
            input_tokens, output_tokens = usage
            yield UsageEvent(
                run_id=req.run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=None,
                model=model,
            )

        yield DoneEvent(run_id=req.run_id, ok=True)


def _parse_input(raw: str) -> tuple[str | None, dict[str, Any]]:
    """Parse the JSON envelope. Returns (user_message, variables)."""
    if not raw:
        return None, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Permissive fallback: treat raw text as the user message.
        return raw, {}
    if not isinstance(data, dict):
        return None, {}
    user_message = data.get("user_message")
    variables = data.get("variables") or {}
    if not isinstance(user_message, str) or not isinstance(variables, dict):
        return None, {}
    return user_message, variables


def _build_deps(dotted: str) -> Any:
    project_root = os.environ.get("AGENTBOX_PROJECT_ROOT", "/project")
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        for sub in ("libs", "src"):
            p = os.path.join(project_root, sub)
            if os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)

    module_name, _, attr = dotted.partition(":")
    if not attr:
        raise ValueError(
            f"deps_factory must be 'module.path:callable', got {dotted!r}"
        )
    module = importlib.import_module(module_name)
    factory = getattr(module, attr)
    return factory()


def _serialize_output(result: Any) -> str:
    """Extract the agent's output as a string."""
    output = getattr(result, "output", result)
    if isinstance(output, str):
        return output
    if hasattr(output, "model_dump_json"):
        return output.model_dump_json()
    if hasattr(output, "model_dump"):
        return json.dumps(output.model_dump())
    return json.dumps(output, default=str)


def _extract_usage(result: Any) -> tuple[int, int] | None:
    """Best-effort token usage extraction from a pydantic-ai RunResult."""
    usage_fn = getattr(result, "usage", None)
    if usage_fn is None:
        return None
    try:
        usage = usage_fn() if callable(usage_fn) else usage_fn
    except Exception:
        return None
    input_tokens = (
        getattr(usage, "input_tokens", None)
        or getattr(usage, "request_tokens", None)
        or 0
    )
    output_tokens = (
        getattr(usage, "output_tokens", None)
        or getattr(usage, "response_tokens", None)
        or 0
    )
    return int(input_tokens), int(output_tokens)
