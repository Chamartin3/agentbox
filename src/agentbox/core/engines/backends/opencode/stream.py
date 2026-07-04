"""OpenCode subprocess runner — spawns, streams events, handles timeout/rate-limit."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time as _time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from agentbox.core.data.constants import LogLevel, RunStatus
from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    TimeoutEvent,
)
from agentbox.core.engines.backends.opencode.session import (
    parse_event_stream_with_thinking,
    strip_code_fences,
)
from agentbox.core.engines.streaming.rate_limit import (
    detect_in_opencode_event,
    detect_in_text_line,
)

class _SessionCarrier(Protocol):
    """Minimal surface stream needs from the backend — the mutable session id.

    Declared here (the lower module) so streaming depends on no adapter type;
    ``OpenCodeBackend`` satisfies it structurally.
    """

    _session_id: str | None


_HEARTBEAT_INTERVAL_SECONDS = 30.0


async def _run_opencode_stream(
    backend: _SessionCarrier,
    run_id: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int | None = 1200,
    stdin_data: bytes | None = None,
) -> AsyncIterator[RunEvent]:
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
        yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
        return

    assert proc.stdout is not None and proc.stderr is not None

    _cleaned_up = False

    def _kill_proc() -> None:
        nonlocal _cleaned_up
        if _cleaned_up:
            return
        _cleaned_up = True
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    if stdin_data is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_data)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
            proc.stdin.close()

    stderr_lines: list[str] = []
    stderr_queue: asyncio.Queue[str] = asyncio.Queue()

    _proc_start = _time.time()
    _opencode_log_dir = Path(
        os.environ.get(
            "OPENCODE_LOG_DIR",
            os.path.expanduser("~/.local/share/opencode/log"),
        )
    )

    async def _tail_opencode_log() -> None:
        log_path: Path | None = None
        for _ in range(50):
            if _opencode_log_dir.is_dir():
                candidates = sorted(
                    (
                        p
                        for p in _opencode_log_dir.iterdir()
                        if p.is_file() and p.stat().st_mtime >= _proc_start - 1
                    ),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if candidates:
                    log_path = candidates[0]
                    break
            await asyncio.sleep(0.1)
        if log_path is None:
            return
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                while True:
                    line = fh.readline()
                    if not line:
                        await asyncio.sleep(0.5)
                        continue
                    if line.startswith("ERROR"):
                        await stderr_queue.put(f"opencode-log: {line.rstrip()}")
        except (OSError, asyncio.CancelledError):
            return

    log_tail_task = asyncio.create_task(_tail_opencode_log())

    async def _drain_stderr() -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            decoded = line.decode(errors="replace").rstrip()
            stderr_lines.append(decoded)
            if decoded:
                await stderr_queue.put(decoded)

    stderr_task = asyncio.create_task(_drain_stderr())

    def _drain_stderr_queue() -> tuple[list[LogEvent], str | None]:
        out: list[LogEvent] = []
        fatal: str | None = None
        while not stderr_queue.empty():
            try:
                msg = stderr_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            out.append(LogEvent(run_id=run_id, level=LogLevel.WARN, message=msg))
            if fatal is None:
                fatal = detect_in_text_line(msg)
        return out, fatal

    stdout_chunks: list[str] = []
    streamed_text_parts: list[str] = []
    rate_limit_error: str | None = None

    read_task: asyncio.Task[bytes] | None = None
    queue_task: asyncio.Task[str] | None = None
    silent_since: float = _time.time()

    try:
        async with asyncio.timeout(timeout):
            while True:
                if read_task is None:
                    read_task = asyncio.create_task(proc.stdout.readline())
                if queue_task is None:
                    queue_task = asyncio.create_task(stderr_queue.get())
                elapsed = _time.time() - silent_since
                wait_for = max(1.0, _HEARTBEAT_INTERVAL_SECONDS - elapsed)
                done, _pending = await asyncio.wait(
                    {read_task, queue_task},
                    timeout=wait_for,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    drained, fatal = _drain_stderr_queue()
                    for log_ev in drained:
                        yield log_ev
                    if fatal is not None:
                        rate_limit_error = fatal
                        break
                    yield LogEvent(
                        run_id=run_id,
                        level=LogLevel.INFO,
                        message=(
                            f"opencode silent for {int(_HEARTBEAT_INTERVAL_SECONDS)}s "
                            f"(pid={proc.pid}); waiting for next event"
                        ),
                    )
                    silent_since = _time.time()
                    continue
                if queue_task in done:
                    msg = queue_task.result()
                    queue_task = None
                    yield LogEvent(run_id=run_id, level=LogLevel.WARN, message=msg)
                    fatal_msg = detect_in_text_line(msg)
                    drained, fatal = _drain_stderr_queue()
                    for log_ev in drained:
                        yield log_ev
                    fatal_msg = fatal_msg or fatal
                    if fatal_msg is not None:
                        rate_limit_error = fatal_msg
                        break
                    if read_task not in done:
                        continue
                if read_task not in done:
                    continue
                line_bytes = read_task.result()
                read_task = None
                silent_since = _time.time()
                drained, fatal = _drain_stderr_queue()
                for log_ev in drained:
                    yield log_ev
                if fatal is not None:
                    rate_limit_error = fatal
                    break
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
                detected = detect_in_opencode_event(evt)
                if detected is not None:
                    rate_limit_error = detected
                    break
                if backend._session_id is None:
                    sid = evt.get("sessionID")
                    if isinstance(sid, str) and sid:
                        backend._session_id = sid
                if evt.get("type") == "text":
                    part = evt.get("part")
                    if isinstance(part, dict):
                        ptype = part.get("type")
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            if ptype == "text":
                                streamed_text_parts.append(text)
                                yield TextEvent(
                                    run_id=run_id, text=text, delta=True
                                )
                            elif ptype in ("thinking", "reasoning"):
                                yield ThinkingEvent(run_id=run_id, text=text)
            await proc.wait()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        stderr_task.cancel()
        log_tail_task.cancel()
        if read_task is not None:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await read_task
        if queue_task is not None:
            queue_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await queue_task
        raw = "".join(stdout_chunks).strip()
        if raw and not streamed_text_parts:
            text_parts, thinking_parts, parsed_sid, _parse_failed = (
                parse_event_stream_with_thinking(raw)
            )
            if parsed_sid:
                backend._session_id = parsed_sid
            for tt in thinking_parts:
                yield ThinkingEvent(run_id=run_id, text=tt)
            if text_parts:
                yield TextEvent(run_id=run_id, text="".join(text_parts))
        for sl in stderr_lines:
            if sl.strip():
                yield LogEvent(run_id=run_id, level=LogLevel.WARN, message=sl)
        yield TimeoutEvent(run_id=run_id, timeout_seconds=timeout or 0, error=f"timeout after {timeout}s")
        yield DoneEvent(run_id=run_id, ok=False, error=f"timeout after {timeout}s", status=RunStatus.TIMEOUT)
        return

    if rate_limit_error is not None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        stderr_task.cancel()
        log_tail_task.cancel()
        if read_task is not None:
            read_task.cancel()
        if queue_task is not None:
            queue_task.cancel()
        yield DoneEvent(run_id=run_id, ok=False, error=rate_limit_error)
        return

    log_tail_task.cancel()
    if queue_task is not None:
        queue_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await queue_task
    with contextlib.suppress(asyncio.CancelledError):
        await stderr_task

    for sl in stderr_lines:
        if sl.strip():
            yield LogEvent(run_id=run_id, level=LogLevel.WARN, message=sl)

    raw = "".join(stdout_chunks).strip()
    if not raw:
        yield DoneEvent(run_id=run_id, ok=proc.returncode == 0, exit_code=proc.returncode, error="opencode produced no stdout" if proc.returncode != 0 else None)
        return

    text_parts, thinking_parts, parsed_sid, parse_failed = (
        parse_event_stream_with_thinking(raw)
    )
    if parsed_sid:
        backend._session_id = parsed_sid
    if parse_failed and not text_parts:
        yield LogEvent(run_id=run_id, level=LogLevel.WARN, message="opencode --format json output was not parseable; using raw stdout")
        yield TextEvent(run_id=run_id, text=raw)
        yield DoneEvent(run_id=run_id, ok=proc.returncode == 0, exit_code=proc.returncode)
        return

    if not streamed_text_parts:
        for thinking_text in thinking_parts:
            yield ThinkingEvent(run_id=run_id, text=thinking_text)

    stripped_text = strip_code_fences("".join(text_parts))
    yield TextEvent(run_id=run_id, text=stripped_text)
    yield DoneEvent(run_id=run_id, ok=proc.returncode == 0, exit_code=proc.returncode)
