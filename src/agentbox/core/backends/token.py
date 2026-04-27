"""Backend adapter for the in-process token (pydantic-ai) runner.

``render()`` extracts the system prompt and ``deps_factory`` into
``agent_meta``. ``run()`` builds a ``pydantic_ai.Agent`` and executes
``run_sync`` with the user message (and optional deps).
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.backends.base import RenderedConfig

_NAME = "token"


class TokenBackend:
    name = _NAME

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
    ) -> RenderedConfig:
        spec = agent.runner

        composed_system = getattr(agent, "_composed_system", None)
        if composed_system is not None:
            prompt = composed_system
        else:
            prompt_text = getattr(agent, "load_prompt", None)
            prompt = prompt_text(workdir.parent) if prompt_text else ""

        agent_meta: dict[str, Any] = {
            "deps_factory": spec.deps_factory,
            "model": spec.model,
            "prompt": prompt,
            "agent_id": agent.id,
        }

        files: dict[Path, bytes] = {}
        if composed_system is not None:
            files[Path("CLAUDE.md")] = composed_system.encode("utf-8")
        else:
            claude_md = workdir / "CLAUDE.md"
            if claude_md.exists():
                files[Path("CLAUDE.md")] = claude_md.read_bytes()

        return RenderedConfig(
            cwd=Path("."),
            files=files,
            agent_meta=agent_meta,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        prompt = rendered.agent_meta.get("prompt", "")
        deps_factory = rendered.agent_meta.get("deps_factory")
        model = rendered.agent_meta.get("model")

        yield LogEvent(
            run_id=run_id,
            message="token backend: running pydantic-ai Agent in-process",
        )

        try:
            from pydantic_ai import Agent
        except ImportError as exc:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=f"pydantic-ai is required for token backend: {exc}",
            )
            return

        user_message, _variables = _parse_input(input)
        if user_message is None:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=(
                    "token backend input must be a JSON object with a "
                    "'user_message' string (and optional 'variables' dict)"
                ),
            )
            return

        deps = None
        if deps_factory:
            try:
                deps = _build_deps(deps_factory)
            except Exception as exc:
                yield DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=f"deps_factory error: {exc}",
                )
                return

        try:
            agent = Agent(model=model, system_prompt=prompt)
        except Exception as exc:
            yield DoneEvent(
                run_id=run_id,
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
                run_id=run_id,
                ok=False,
                error=f"agent execution error: {exc}",
            )
            return
        _elapsed = time.monotonic() - start

        yield TextEvent(run_id=run_id, text=_serialize_output(result))

        usage = _extract_usage(result)
        if usage is not None:
            input_tokens, output_tokens = usage
            yield UsageEvent(
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=None,
                model=model,
            )

        yield DoneEvent(run_id=run_id, ok=True)


def _parse_input(raw: str) -> tuple[str | None, dict[str, Any]]:
    if not raw:
        return None, {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
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
    output = getattr(result, "output", result)
    if isinstance(output, str):
        return output
    if hasattr(output, "model_dump_json"):
        return output.model_dump_json()
    if hasattr(output, "model_dump"):
        return json.dumps(output.model_dump())
    return json.dumps(output, default=str)


def _extract_usage(result: Any) -> tuple[int, int] | None:
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
