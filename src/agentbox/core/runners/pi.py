"""pi.dev CLI runner — headless execution via ``pi -p ... --mode json``.

Invocation shape::

    pi -p "<prompt>" --mode json [--model <model>] [extra_args]

``-p`` is pi's "print" / one-shot mode; ``--mode json`` switches the
stdout transport from the TUI renderer to newline-delimited JSON event
objects. The prompt is also piped via stdin (pi accepts stdin in -p
mode) to avoid argv-length limits.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    UsageEvent,
)
from agentbox.core.constants import RunnerKind
from agentbox.core.streaming.jsonl import stream_jsonl_subprocess
from agentbox.core.runners.base import Runner, RunRequest

_DEFAULT_PI_MODEL: str | None = None


def parse_pi_event(evt: dict[str, Any], run_id: str) -> tuple[list[RunEvent], str | None]:
    """Parse one ``pi --mode json`` event line.

    pi's event schema is documented loosely; we accept the common shapes
    seen across versions:
      - ``{"type":"session","id":"..."}`` / ``{"type":"session.started",...}``
      - ``{"type":"text" | "message" | "assistant", "text":"..."}``
      - ``{"type":"delta", "text":"..."}``
      - ``{"type":"thinking" | "reasoning", "text":"..."}``
      - ``{"type":"usage", "model":"...", "input_tokens":N, "output_tokens":N}``
    Unknown event types are ignored.
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
                input_tokens=_int_or_none(usage.get("input_tokens")),
                output_tokens=_int_or_none(usage.get("output_tokens")),
                cache_read_tokens=_int_or_none(usage.get("cache_read_tokens")),
            )
        )

    return events, session_id


def _int_or_none(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class PiRunner(Runner):
    kind = RunnerKind.PI
    conversation_format = "pi-session"

    def __init__(self) -> None:
        super().__init__()
        self._session_id: str | None = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return self._session_id

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        if shutil.which("pi") is None:
            yield DoneEvent(run_id=req.run_id, ok=False, error="pi CLI not found")
            return

        spec = req.agent.runner
        argv = build_pi_argv(spec, _DEFAULT_PI_MODEL)

        env = dict(os.environ)

        yield LogEvent(
            run_id=req.run_id,
            message=f"$ {' '.join(argv)} (cwd={req.workdir})",
        )

        async for ev, sid in stream_jsonl_subprocess(
            run_id=req.run_id,
            argv=argv,
            cwd=req.workdir,
            env=env,
            timeout=spec.timeout_seconds,
            parse_event=parse_pi_event,
            stdin_data=req.input.encode("utf-8"),
            cli_label="pi",
        ):
            if sid and not self._session_id:
                self._session_id = sid
            yield ev


def build_pi_argv(spec: Any, default_model: str | None) -> list[str]:
    """Construct the pi argv. Public so backend adapter can reuse it."""
    argv: list[str] = ["pi", "-p", "--mode", "json"]
    if spec.model:
        argv += ["--model", spec.model]
    elif default_model and "--model" not in spec.extra_args:
        argv += ["--model", default_model]
    argv += list(spec.extra_args)
    return argv
