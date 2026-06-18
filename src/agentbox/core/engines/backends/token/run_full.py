"""Full-agent execution path for ``TokenBackend``.

Used when the runner spec sets ``agent_module`` — we import the user's
``BaseAgent`` subclass, instantiate it with the resolved provider
kwargs, validate the input against its request model, and run it via
``run_sync``. All events are yielded to the caller so the surrounding
async generator preserves event ordering.

Split out of ``_backend.py`` to keep the main module focused on the
``BackendAdapter`` contract (render, run dispatch) rather than the
mode-specific control flow.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from agentbox.config import SETTINGS
from agentbox.core.constants import LogLevel, MessageRole, RunStatus
from agentbox.core.data import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    UsageEvent,
)
from agentbox.core.engines.backends.token.stream import (
    _emit_message_history,
    _format_provider_error,
)


def import_agent(module_path: str) -> type:
    """Import a pydantic-ai Agent class from ``module.path:ClassName``.

    Adds ``project_root`` (from ``SETTINGS.consumer_project_root``) to
    ``sys.path`` so project-local modules (``apps.*``, ``agents.*``)
    are importable without Django.
    """
    project_root = str(SETTINGS.consumer_project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        libs_dir = os.path.join(project_root, "libs")
        if os.path.isdir(libs_dir) and libs_dir not in sys.path:
            sys.path.insert(0, libs_dir)
        src_dir = os.path.join(project_root, "src")
        if os.path.isdir(src_dir) and src_dir not in sys.path:
            sys.path.insert(0, src_dir)

    module_name, _, class_name = module_path.partition(":")
    if not class_name:
        raise ValueError(
            f"agent_module must be in 'module.path:ClassName' format, "
            f"got {module_path!r}"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(
            f"cannot import agent module {module_name!r}: {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ImportError(
            f"agent class {class_name!r} not found in {module_name!r}"
        ) from exc
    return cls


def resolve_request_model(agent_cls: type) -> type:
    """Return the request model class for a pydantic-ai BaseAgent subclass."""
    if hasattr(agent_cls, "INPUT_TYPE") and agent_cls.INPUT_TYPE is not None:
        return agent_cls.INPUT_TYPE

    # Try to extract from generic base (BaseAgent[RequestModel, ResponseModel]).
    for base in getattr(agent_cls, "__orig_bases__", []):
        args = getattr(base, "__args__", [])
        if args:
            return args[0]

    # Fallback: accept any dict.
    class _GenericInput(BaseModel):
        data: dict[str, Any] = Field(default_factory=dict)

    return _GenericInput


async def run_full_agent_mode(
    *,
    run_id: str,
    agent_module: str,
    prompt: str,
    model_str: str,
    model: str | None,
    provider: str | None,
    api_key: str | None,
    base_url: str | None,
    input_data: Any,
    import_agent_fn: Any = None,
) -> AsyncIterator[RunEvent]:
    """Drive the user-supplied BaseAgent subclass to completion.

    ``import_agent_fn`` lets the caller substitute the importer — needed
    so tests that patch ``TokenBackend._import_agent`` keep affecting
    the actual import call. Defaults to the module-level
    :func:`import_agent`.
    """
    importer = import_agent_fn or import_agent
    try:
        agent_cls = importer(agent_module)
    except (ImportError, ValueError) as exc:
        yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
        return

    # Build and validate the request model.
    request_model = resolve_request_model(agent_cls)
    try:
        request = request_model.model_validate(input_data)
    except Exception as exc:
        yield DoneEvent(
            run_id=run_id,
            ok=False,
            error=f"input validation error: {exc}",
        )
        return

    # Resolve MCP URL from env or config.
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp/")

    # Instantiate the agent.
    try:
        agent_kwargs: dict[str, Any] = {"mcp_url": mcp_url}
        if provider and api_key and base_url:
            agent_kwargs["api_key"] = api_key
            agent_kwargs["base_url"] = base_url
        if model and provider:
            agent_kwargs["model"] = model
        agent_instance = agent_cls(**agent_kwargs)
    except TypeError:
        # Fall back to mcp_url-only init if extended kwargs not supported.
        try:
            agent_instance = agent_cls(mcp_url=mcp_url)
        except Exception as exc:
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=f"agent instantiation error: {exc}",
            )
            return
    except Exception as exc:
        yield DoneEvent(
            run_id=run_id,
            ok=False,
            error=f"agent instantiation error: {exc}",
        )
        return

    # Run the agent synchronously.
    start = time.monotonic()
    try:
        try:
            system_prompt, user_message = agent_instance.render_prompts(request)
        except Exception:
            system_prompt = prompt
            user_message = json.dumps(input_data, indent=2, default=str)
        yield TextEvent(run_id=run_id, role=MessageRole.SYSTEM, text=system_prompt)
        yield TextEvent(run_id=run_id, role=MessageRole.USER, text=user_message)
        result = agent_instance.run_sync(request)
    except Exception as exc:
        err_text = _format_provider_error(exc, model=model_str, provider=provider)
        yield LogEvent(run_id=run_id, level=LogLevel.ERROR, message=err_text)
        yield DoneEvent(run_id=run_id, ok=False, error=err_text, status=RunStatus.ERROR)
        return
    _elapsed = time.monotonic() - start

    for ev in _emit_message_history(
        run_id, getattr(agent_instance, "_message_history", [])
    ):
        yield ev

    # Serialize output (result is the return value directly).
    try:
        if hasattr(result, "model_dump_json"):
            output_text = result.model_dump_json()
        elif hasattr(result, "model_dump"):
            output_text = json.dumps(result.model_dump())
        else:
            output_text = json.dumps(result, default=str)
    except Exception as exc:
        yield DoneEvent(
            run_id=run_id,
            ok=False,
            error=f"output serialization error: {exc}",
        )
        return

    yield TextEvent(run_id=run_id, text=output_text)
    yield UsageEvent(
        run_id=run_id,
        input_tokens=0,
        output_tokens=0,
        cost_usd=None,
        model=getattr(agent_instance, "model", None),
    )
    yield DoneEvent(run_id=run_id, ok=True)
