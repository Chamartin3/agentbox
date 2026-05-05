"""Backend adapter for the pi.dev CLI (``pi -p ... --mode json``).

Plan 16 Phase 2 — first cut. Mirrors :mod:`agentbox.core.backends.codex`.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    UsageEvent,
)
from agentbox.core.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.constants import DEFAULT_RUNNER_TIMEOUT_SECONDS
from agentbox.core.streaming.jsonl import stream_jsonl_subprocess


_NAME = "pi"
_DEFAULT_PI_MODEL: str | None = None


def build_pi_argv(spec: Any, default_model: str | None) -> list[str]:
    """Construct the pi argv. Public so tests can introspect it."""
    argv: list[str] = ["pi", "-p", "--mode", "json"]
    if spec.model:
        argv += ["--model", spec.model]
    elif default_model and "--model" not in spec.extra_args:
        argv += ["--model", default_model]
    argv += list(spec.extra_args)
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
        usage = evt.get("usage") if isinstance(evt.get("usage"), dict) else evt
        model = evt.get("model") if isinstance(evt.get("model"), str) else None
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
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


class PiBackend(BackendAdapter):
    name = _NAME
    conversation_format: str | None = "pi-session"
    default_model = _DEFAULT_PI_MODEL

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
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
        runner_config: Any | None = None,
    ) -> RenderedConfig:
        spec = agent.runner

        if runner_config is not None and getattr(runner_config, "model", None):
            model = runner_config.model
        else:
            model = self._resolve_model(spec)

        argv = build_pi_argv(spec, self.default_model)

        if runner_config is not None and getattr(runner_config, "extra_args", None):
            argv += list(runner_config.extra_args)

        env = dict(os.environ)

        timeout_seconds = spec.timeout_seconds
        if runner_config is not None and getattr(
            runner_config, "timeout_seconds", None
        ):
            timeout_seconds = runner_config.timeout_seconds

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            files=self._collect_system_files(agent, workdir),
            agent_meta={"timeout_seconds": timeout_seconds},
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

        timeout = rendered.agent_meta.get(
            "timeout_seconds", DEFAULT_RUNNER_TIMEOUT_SECONDS
        )

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
