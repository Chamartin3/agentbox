"""Backend adapter for the pi.dev CLI (``pi -p ... --mode json``).

Mirrors :mod:`agentbox.core.engines.backends.codex`.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.config import SETTINGS

from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    UsageEvent,
)
from agentbox.core.engines.contracts.base import BackendAdapter, RenderedConfig
from agentbox.core.engines.streaming.jsonl import stream_jsonl_subprocess
from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.translation import intersect_allowed_tools

_NAME = "pi"


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
    evt: dict[str, Any], run_id: str
) -> tuple[list[RunEvent], str | None]:
    """Parse one ``pi --mode json`` event line.

    pi's event schema is documented loosely; accept the common shapes:

      - ``{"type":"session","id":"..."}`` / ``{"type":"session.started",...}``
      - ``{"type":"text"|"message"|"assistant","text":"..."}``
      - ``{"type":"delta","text":"..."}``
      - ``{"type":"thinking"|"reasoning","text":"..."}``
      - ``{"type":"usage","model":"...","input_tokens":N,"output_tokens":N}``
    """
    events: list[RunEvent] = []
    session_id: str | None = None

    etype = evt.get("type")

    if etype in ("session", "session.started", "thread.started"):
        sid = evt.get("id") or evt.get("session_id") or evt.get("thread_id")
        if isinstance(sid, str) and sid:
            session_id = sid

    text = evt.get("text")
    if etype in ("text", "delta", "message", "assistant", "assistant_message"):
        if isinstance(text, str) and text:
            events.append(TextEvent(run_id=run_id, text=text, delta=True))
        else:
            content = evt.get("content")
            if isinstance(content, str) and content:
                events.append(TextEvent(run_id=run_id, text=content, delta=True))

    if etype in ("thinking", "reasoning") and isinstance(text, str) and text:
        events.append(ThinkingEvent(run_id=run_id, text=text))

    if etype in ("usage", "turn.completed", "completion"):
        usage_raw = evt.get("usage")
        usage: dict[str, Any] = usage_raw if isinstance(usage_raw, dict) else evt
        model_raw = evt.get("model")
        model = model_raw if isinstance(model_raw, str) else None
        events.append(
            UsageEvent(
                run_id=run_id,
                model=model,
                input_tokens=_int_or_zero(usage.get("input_tokens")),
                output_tokens=_int_or_zero(usage.get("output_tokens")),
                cache_read_tokens=_int_or_zero(usage.get("cache_read_tokens")),
            )
        )

    return events, session_id


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
        host_capabilities: dict | None = None,
        ws_allowed_tools: set[CanonicalTool] | None = None,
        **kwargs: Any,
    ) -> RenderedConfig:
        agent_runner = getattr(agent, "runner", None)
        model = getattr(runner_config, "model", None) or SETTINGS.pi_model
        extra_args = list(getattr(runner_config, "extra_args", None) or [])

        argv = build_pi_argv(model, extra_args, SETTINGS.pi_model)

        env = dict(os.environ)

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
