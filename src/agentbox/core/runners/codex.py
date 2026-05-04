"""OpenAI Codex CLI runner — headless execution via ``codex exec``.

Invocation shape::

    codex exec --json [--model <model>] [extra_args]

The prompt is piped via stdin so large prompts don't trip E2BIG. ``--json``
emits newline-delimited JSON events; we extract assistant text and the
session/conversation id and concatenate text parts into the final output.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.constants import RunnerKind
from agentbox.core.streaming.jsonl import stream_jsonl_subprocess
from agentbox.core.runners.base import Runner, RunRequest

_DEFAULT_CODEX_MODEL: str | None = None  # let codex pick its own default


def parse_codex_event(evt: dict[str, Any], run_id: str) -> tuple[list[RunEvent], str | None]:
    """Parse one codex --json event line.

    The codex JSON schema isn't strictly stable across versions; we look
    at the common shapes:
      - ``{"type":"item.completed","item":{"item_type":"assistant_message","text":"..."}}``
      - ``{"type":"item.completed","item":{"item_type":"reasoning","text":"..."}}``
      - ``{"type":"thread.started","thread_id":"..."}``
      - ``{"type":"turn.completed","usage":{"input_tokens":...,"output_tokens":...}}``
    Unknown event types are ignored.
    """
    events: list[RunEvent] = []
    session_id: str | None = None

    etype = evt.get("type")
    if etype in ("thread.started", "session.started", "session"):
        sid = evt.get("thread_id") or evt.get("session_id") or evt.get("id")
        if isinstance(sid, str) and sid:
            session_id = sid

    item = evt.get("item")
    if isinstance(item, dict):
        item_type = item.get("item_type") or item.get("type")
        text = item.get("text")
        if item_type == "assistant_message" and isinstance(text, str) and text:
            events.append(TextEvent(run_id=run_id, text=text, delta=True))
        # codex emits a single "agent_message" event in some versions
        if item_type in ("agent_message", "message") and isinstance(text, str) and text:
            events.append(TextEvent(run_id=run_id, text=text, delta=True))

    # Older / alternate shape: top-level "delta" or "text"
    delta = evt.get("delta")
    if isinstance(delta, dict):
        t = delta.get("text") or delta.get("content")
        if isinstance(t, str) and t:
            events.append(TextEvent(run_id=run_id, text=t, delta=True))

    usage = evt.get("usage")
    if isinstance(usage, dict):
        model = evt.get("model") if isinstance(evt.get("model"), str) else None
        events.append(
            UsageEvent(
                run_id=run_id,
                model=model,
                input_tokens=_int_or_none(usage.get("input_tokens")),
                output_tokens=_int_or_none(usage.get("output_tokens")),
                cache_read_tokens=_int_or_none(usage.get("cached_input_tokens")),
            )
        )

    return events, session_id


def _int_or_none(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class CodexRunner(Runner):
    kind = RunnerKind.CODEX
    conversation_format = "codex-session"

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
        if shutil.which("codex") is None:
            yield DoneEvent(run_id=req.run_id, ok=False, error="codex CLI not found")
            return

        spec = req.agent.runner
        argv = build_codex_argv(spec, _DEFAULT_CODEX_MODEL)

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
            parse_event=parse_codex_event,
            stdin_data=req.input.encode("utf-8"),
            cli_label="codex",
        ):
            if sid and not self._session_id:
                self._session_id = sid
            yield ev


def build_codex_argv(spec: Any, default_model: str | None) -> list[str]:
    """Construct the codex argv. Public so backend adapter can reuse it."""
    argv: list[str] = ["codex", "exec", "--json"]
    if spec.model:
        argv += ["--model", spec.model]
    elif default_model and "--model" not in spec.extra_args:
        argv += ["--model", default_model]
    argv += list(spec.extra_args)
    return argv
