"""Backend adapter for the OpenAI Codex CLI (``codex exec --json``).

Self-contained adapter introduced in Plan 16 Phase 2. Streaming uses
the shared :func:`agentbox.core.execution.streaming.jsonl.stream_jsonl_subprocess`
helper.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.data import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.engines.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.execution.streaming.jsonl import stream_jsonl_subprocess

_NAME = "codex"
_DEFAULT_CODEX_MODEL: str | None = None  # let codex pick its own default


def build_codex_argv(
    model: str | None, extra_args: list[str] | None, default_model: str | None
) -> list[str]:
    """Construct the codex argv. Public so tests can introspect it."""
    args = list(extra_args or [])
    effective_model = model or default_model
    argv: list[str] = ["codex", "exec", "--json"]
    if effective_model and "--model" not in args:
        argv += ["--model", effective_model]
    argv += args
    return argv


def parse_codex_event(
    evt: dict[str, Any], run_id: str
) -> tuple[list[RunEvent], str | None]:
    """Parse one ``codex exec --json`` event line.

    Codex's JSON schema isn't strictly stable across versions. We accept
    the common shapes seen in the wild:

      - ``{"type":"thread.started","thread_id":"..."}``
      - ``{"type":"item.completed","item":{"item_type":"assistant_message","text":"..."}}``
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
        if (
            item_type in ("assistant_message", "agent_message", "message")
            and isinstance(text, str)
            and text
        ):
            events.append(TextEvent(run_id=run_id, text=text, delta=True))

    # Alternate shape: top-level "delta" or "text"
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
                input_tokens=_int_or_zero(usage.get("input_tokens")),
                output_tokens=_int_or_zero(usage.get("output_tokens")),
                cache_read_tokens=_int_or_zero(usage.get("cached_input_tokens")),
            )
        )

    return events, session_id


def _int_or_zero(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


class CodexBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "codex-session"
    default_model = _DEFAULT_CODEX_MODEL

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
        **kwargs: Any,
    ) -> RenderedConfig:
        agent_runner = getattr(agent, "runner", None)
        model = getattr(runner_config, "model", None) or self.default_model
        extra_args = list(getattr(runner_config, "extra_args", None) or [])

        argv = build_codex_argv(model, extra_args, self.default_model)

        env = dict(os.environ)

        timeout_seconds = getattr(agent_runner, "timeout_seconds", None)

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            files=self._collect_system_files(agent, workdir, composed),
            agent_meta={"timeout_seconds": timeout_seconds},
            model=model,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        if shutil.which("codex") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="codex CLI not found")
            return

        yield LogEvent(
            run_id=run_id,
            message=f"$ {' '.join(rendered.argv)} (cwd={rendered.cwd})",
        )

        timeout = rendered.agent_meta["timeout_seconds"]

        async for ev, sid in stream_jsonl_subprocess(
            run_id=run_id,
            argv=list(rendered.argv),
            cwd=rendered.cwd,
            env=dict(rendered.env),
            timeout=timeout,
            parse_event=parse_codex_event,
            stdin_data=input.encode("utf-8"),
            cli_label="codex",
        ):
            if sid and not self._session_id:
                self._session_id = sid
            yield ev
