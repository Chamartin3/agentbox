"""Backend adapter for the pi.dev CLI (``pi -p ... --mode json``).

Mirrors :mod:`agentbox.core.engines.backends.codex`.
"""

from __future__ import annotations

from agentbox.core.data.jsontypes import RawJson

import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar, TypedDict

from agentbox.core.config import SETTINGS
from agentbox.core.data import RawJsonValue

from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.data import RenderedConfig
from agentbox.core.engines.backends.streaming.jsonl import stream_jsonl_subprocess
from agentbox.core.data import CanonicalTool
from agentbox.core.tools.translation import intersect_allowed_tools

_NAME = "pi"


class _PiCompat(TypedDict):
    """pi provider compatibility flags."""
    supportsDeveloperRole: bool
    supportsReasoningEffort: bool


class _PiModel(TypedDict):
    """pi model identifier."""
    id: str


class _PiOllamaProvider(TypedDict):
    """pi ollama provider configuration block."""
    baseUrl: str
    api: str
    apiKey: str
    compat: _PiCompat
    models: list[_PiModel]


class _PiProvidersBlock(TypedDict):
    """pi providers block (ollama custom provider config)."""
    ollama: _PiOllamaProvider


class PiModelsJson(TypedDict):
    """pi models.json configuration (custom provider schema)."""
    providers: _PiProvidersBlock



def _as_str(v: RawJsonValue) -> str | None:
    return v if isinstance(v, str) else None


def _normalize_pi_model_id(model: str | None, provider: str | None) -> str | None:
    """agentbox stores ``ollama:qwen3:8b``; pi addresses ``ollama/qwen3:8b``."""
    if model and provider and ":" in model and "/" not in model:
        return f"{provider}/{model.split(':', 1)[1]}"
    return model


def _build_pi_models_json(runner_config: Any, model: str | None) -> PiModelsJson | None:
    """pi custom-provider block (``~/.pi/agent/models.json`` schema).

    ponytail: ollama only — the one keyless local provider the QA suite runs.
    pi speaks to it OpenAI-compatibly; ``apiKey`` is required but ignored.
    ``compat`` flags keep reasoning models working on ollama's OpenAI shim.
    """
    provider = getattr(runner_config, "provider", None)
    base_url = getattr(runner_config, "base_url", None)
    if provider != "ollama" or not base_url or not model:
        return None
    model_id = model.split("/", 1)[1] if "/" in model else model
    return PiModelsJson(
        providers=_PiProvidersBlock(
            ollama=_PiOllamaProvider(
                baseUrl=base_url,
                api="openai-completions",
                apiKey="ollama",
                compat=_PiCompat(
                    supportsDeveloperRole=False,
                    supportsReasoningEffort=False,
                ),
                models=[_PiModel(id=model_id)],
            )
        )
    )


def build_pi_argv(
    model: str | None, extra_args: list[str] | None, default_model: str | None
) -> list[str]:
    """Construct the pi argv. Public so tests can introspect it."""
    args = list(extra_args or [])
    effective_model = model or default_model
    argv: list[str] = ["pi", "-p", "--mode", "json"]
    if effective_model and "--model" not in args:
        argv += ["--model", effective_model]
    argv += args
    return argv


def parse_pi_event(
    evt: RawJson, run_id: str
) -> tuple[list[RunEvent], str | None]:
    """Parse one ``pi --mode json`` event line (pi v3 schema).

    pi v3 streams:
      - ``{"type":"session","id":"...","cwd":"..."}``
      - ``{"type":"message_update","assistantMessageEvent":{"type":"text_delta"|
        "thinking_delta","delta":"..."}}``
      - ``{"type":"tool_execution_start","toolCallId":"...","toolName":"...",
        "args":{...}}``
      - ``{"type":"tool_execution_end","toolCallId":"...","toolName":"...",
        "result":{"content":[{"type":"text","text":"..."}]},"isError":false}``
      - ``{"type":"turn_end","message":{"role":"assistant","usage":{...}}}``
    """
    events: list[RunEvent] = []
    session_id: str | None = None

    etype = evt.get("type")

    if etype == "session":
        sid = evt.get("id")
        if isinstance(sid, str) and sid:
            session_id = sid

    elif etype == "message_update":
        ame = evt.get("assistantMessageEvent")
        if isinstance(ame, dict):
            delta = ame.get("delta")
            if isinstance(delta, str) and delta:
                if ame.get("type") == "text_delta":
                    events.append(TextEvent(run_id=run_id, text=delta, delta=True))
                elif ame.get("type") == "thinking_delta":
                    events.append(ThinkingEvent(run_id=run_id, text=delta))

    elif etype == "tool_execution_start":
        name = evt.get("toolName")
        if isinstance(name, str) and name:
            args = evt.get("args")
            events.append(
                ToolCallEvent(
                    run_id=run_id,
                    tool=name,
                    arguments=args if isinstance(args, dict) else {},
                    call_id=_as_str(evt.get("toolCallId")),
                )
            )

    elif etype == "tool_execution_end":
        name = evt.get("toolName")
        if isinstance(name, str) and name:
            events.append(
                ToolResultEvent(
                    run_id=run_id,
                    tool=name,
                    call_id=_as_str(evt.get("toolCallId")),
                    ok=not evt.get("isError", False),
                    result_excerpt=_pi_result_text(evt.get("result")),
                )
            )

    elif etype in ("turn_end", "message_end"):
        msg = evt.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if isinstance(usage, dict):
            events.append(
                UsageEvent(
                    run_id=run_id,
                    model=_as_str(msg.get("model")) if isinstance(msg, dict) else None,
                    input_tokens=_int_or_zero(usage.get("input")),
                    output_tokens=_int_or_zero(usage.get("output")),
                    cache_read_tokens=_int_or_zero(usage.get("cacheRead")),
                )
            )

    return events, session_id


def _pi_result_text(result: object, limit: int = 500) -> str | None:
    """Pull the first text chunk out of a pi ``tool_execution_end`` result."""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and isinstance(c.get("text"), str):
                    return c["text"][:limit]
    return None


def _int_or_zero(v: object) -> int:
    if isinstance(v, (int, float, str)):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
    return 0


class PiBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "pi-session"

    def __init__(self) -> None:
        self._session_id: str | None = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return self._session_id

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: Any = None,
        creds: dict | None = None,
        runner_config: Any | None = None,
        composed: Any | None = None,
        *,
        runtime_config: Any = None,
        ws_allowed_tools: set[CanonicalTool] | None = None,
        **kwargs: Any,
    ) -> RenderedConfig:
        agent_runner = getattr(agent, "runner", None)
        model = getattr(runner_config, "model", None) or SETTINGS.pi_model
        extra_args = list(getattr(runner_config, "extra_args", None) or [])

        provider = getattr(runner_config, "provider", None)
        model = _normalize_pi_model_id(model, provider)

        argv = build_pi_argv(model, extra_args, SETTINGS.pi_model)

        env = dict(os.environ)

        # Inject a per-run custom-provider config so pi can reach a local
        # (non-cloud) provider like ollama. pi reads models.json from its agent
        # dir; PI_CODING_AGENT_DIR relocates that to the run workdir for
        # isolation instead of clobbering shared ~/.pi/agent.
        models_json = _build_pi_models_json(runner_config, model)
        if models_json:
            agent_dir = workdir / ".pi-agent"
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "models.json").write_text(
                json.dumps(models_json, indent=2) + "\n"
            )
            env["PI_CODING_AGENT_DIR"] = str(agent_dir)

        timeout_seconds = getattr(agent_runner, "timeout_seconds", None)

        # Effective tools = agent ∩ workspace (canonical).
        effective_tools: set = set()
        if runtime_config is not None:
            effective_tools = intersect_allowed_tools(
                set(runtime_config.allowed_tools),
                ws_allowed_tools,
            )

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            agent_meta={
                "timeout_seconds": timeout_seconds,
                "effective_tools": sorted(effective_tools),
            },
            model=model,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        if shutil.which("pi") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="pi CLI not found")
            return

        yield LogEvent(
            run_id=run_id,
            message=f"$ {' '.join(rendered.argv)} (cwd={rendered.cwd})",
        )

        timeout = rendered.agent_meta.get("timeout_seconds")

        async for ev, sid in stream_jsonl_subprocess(
            run_id=run_id,
            argv=list(rendered.argv),
            cwd=rendered.cwd,
            env=dict(rendered.env),
            timeout=timeout,
            parse_event=parse_pi_event,
            stdin_data=input.encode("utf-8"),
            cli_label="pi",
        ):
            if sid and not self._session_id:
                self._session_id = sid
            yield ev
