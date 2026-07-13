"""Shared JSONL-stream subprocess helper used by codex / pi runners.

Both the OpenAI ``codex`` and pi.dev ``pi`` CLIs expose a headless mode
that emits newline-delimited JSON events on stdout. Their event schemas
differ from claude_code / opencode but the *plumbing* is identical:
spawn the CLI, stream stdout line-by-line, route JSON events through a
caller-supplied parser, emit a terminal ``DoneEvent``.

This module owns the subprocess plumbing only — backend-specific event
parsing lives in the caller.
"""

from __future__ import annotations

from agentbox.core.data.jsontypes import JsonDict

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from agentbox.core.data.constants import LogLevel, RunStatus
from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    TimeoutEvent,
)

# Heartbeat cadence — see core/backends/opencode.py for the rationale.
_HEARTBEAT_INTERVAL_SECONDS = 30.0


ParsedEvent = tuple[list[RunEvent], str | None]
"""Return value of an event parser: (events to yield, captured session id)."""

EventParser = Callable[[JsonDict, str], ParsedEvent]
"""Parses one decoded JSON event. ``run_id`` is passed for event construction."""


async def stream_jsonl_subprocess(
    *,
    run_id: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int | None,
    parse_event: EventParser,
    stdin_data: bytes | None = None,
    cli_label: str = "subprocess",
) -> AsyncIterator[tuple[RunEvent, str | None]]:
    """Spawn ``argv`` and yield (event, captured_session_id_or_None).

    The caller iterates and forwards events; the session id is reported
    out-of-band so the caller can stash it on the backend instance for
    ``conversation_uri()``.

    Always yields a terminal ``DoneEvent`` (ok=True/False/timeout).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=16 * 1024 * 1024,
        )
    except FileNotFoundError as exc:
        yield DoneEvent(run_id=run_id, ok=False, error=str(exc)), None
        return

    assert proc.stdout is not None and proc.stderr is not None

    if stdin_data is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
            proc.stdin.close()

    stderr_lines: list[str] = []

    async def _drain_stderr() -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            stderr_lines.append(line.decode(errors="replace").rstrip())

    stderr_task = asyncio.create_task(_drain_stderr())

    stdout_chunks: list[str] = []
    captured_session_id: str | None = None
    streamed_any_text = False

    silent_since = time.time()

    try:
        async with asyncio.timeout(timeout):
            while True:
                elapsed = time.time() - silent_since
                wait_for = max(1.0, _HEARTBEAT_INTERVAL_SECONDS - elapsed)
                try:
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=wait_for
                    )
                except TimeoutError:
                    silent_since = time.time()
                    yield (
                        LogEvent(
                            run_id=run_id,
                            level=LogLevel.INFO,
                            message=(
                                f"{cli_label} silent for "
                                f"{int(_HEARTBEAT_INTERVAL_SECONDS)}s "
                                f"(pid={proc.pid}); waiting for next event"
                            ),
                        ),
                        None,
                    )
                    continue
                silent_since = time.time()
                if not line_bytes:
                    break
                line = line_bytes.decode(errors="replace")
                stdout_chunks.append(line)
                s = line.strip()
                if not s:
                    continue
                try:
                    evt = json.loads(s)
                except json.JSONDecodeError:
                    continue
                if not isinstance(evt, dict):
                    continue
                events, sid = parse_event(evt, run_id)
                if sid and not captured_session_id:
                    captured_session_id = sid
                for ev in events:
                    if isinstance(ev, TextEvent):
                        streamed_any_text = True
                    yield ev, captured_session_id
            await proc.wait()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        stderr_task.cancel()
        for sl in stderr_lines:
            if sl.strip():
                yield (
                    LogEvent(run_id=run_id, level=LogLevel.WARN, message=sl),
                    captured_session_id,
                )
        yield (
            TimeoutEvent(
                run_id=run_id,
                timeout_seconds=timeout or 0,
                error=f"timeout after {timeout}s",
            ),
            captured_session_id,
        )
        yield (
            DoneEvent(
                run_id=run_id,
                ok=False,
                error=f"timeout after {timeout}s",
                status=RunStatus.TIMEOUT,
            ),
            captured_session_id,
        )
        return

    with contextlib.suppress(asyncio.CancelledError):
        await stderr_task

    for sl in stderr_lines:
        if sl.strip():
            yield LogEvent(run_id=run_id, level=LogLevel.WARN, message=sl), captured_session_id

    if not streamed_any_text:
        raw = "".join(stdout_chunks).strip()
        # Stream produced no parseable text events. If raw stdout exists,
        # surface it as a TextEvent so the run isn't silently empty.
        if raw and not _looks_like_jsonl(raw):
            yield TextEvent(run_id=run_id, text=raw), captured_session_id

    yield (
        DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            error=(
                f"{cli_label} exited with status {proc.returncode}"
                if proc.returncode not in (0, None)
                else None
            ),
        ),
        captured_session_id,
    )


def _looks_like_jsonl(raw: str) -> bool:
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
            return True
        except json.JSONDecodeError:
            return False
    return False
