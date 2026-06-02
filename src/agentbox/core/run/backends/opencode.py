"""Backend adapter for the OpenCode CLI.

Self-contained after Plan 16 Phase 4 — ``render()`` builds argv/env
from the ``AgentDef`` and ``run()`` streams events from the OpenCode
subprocess directly.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.data import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    TimeoutEvent,
)
from agentbox.core.run.backends.base import BackendAdapter, RenderedConfig

_NAME = "opencode"
_DEFAULT_OPENCODE_MODEL = "opencode/deepseek-v4-flash-free"

# Emit a heartbeat LogEvent whenever the child produces no stdout for this
# many seconds. Without this, a silent child (stuck on DNS, in opencode's
# internal 429 retry loop, model spinning on a tool call, etc.) leaves the
# transcript empty until the hard timeout fires — operators have no idea
# what was happening. 30s strikes a balance: long enough that normal
# inter-event gaps don't spam the transcript, short enough that a hung run
# logs ~10 heartbeats before a default 5-min timeout.
_HEARTBEAT_INTERVAL_SECONDS = 30.0


class OpenCodeBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "opencode-session"
    default_model = _DEFAULT_OPENCODE_MODEL

    def __init__(self) -> None:
        # Session id is discovered while parsing the opencode JSON event
        # stream. Until then there's no native conversation to load.
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
    ) -> RenderedConfig:
        agent_runner = getattr(agent, "runner", None)
        extra_args = list(
            getattr(runner_config, "extra_args", None)
            or getattr(agent_runner, "extra_args", None)
            or []
        )
        model = (
            getattr(runner_config, "model", None)
            or getattr(agent_runner, "model", None)
            or self.default_model
        )

        argv: list[str] = [
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--format",
            "json",
        ]
        if "--model" not in extra_args and model:
            argv += ["--model", model]
        argv += extra_args

        env = dict(os.environ)
        env["PWD"] = str(workdir)

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
        import shutil

        if shutil.which("opencode") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="opencode CLI not found")
            return

        yield LogEvent(
            run_id=run_id,
            message=f"$ opencode run --stdin ... (cwd={rendered.cwd})",
        )

        stdin_data = input.encode("utf-8")

        async for ev in self._run_opencode(
            run_id,
            rendered.argv,
            rendered.cwd,
            dict(rendered.env),
            timeout=rendered.agent_meta["timeout_seconds"],
            stdin_data=stdin_data,
        ):
            yield ev

    async def _run_opencode(
        self,
        run_id: str,
        argv: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int = 1200,
        stdin_data: bytes | None = None,
    ) -> AsyncIterator[RunEvent]:
        import asyncio
        import json

        from agentbox.core.run.streaming.rate_limit import (
            detect_in_opencode_event,
            detect_in_text_line,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                # asyncio defaults StreamReader's line buffer to 64 KiB.
                # opencode emits whole tool_result / message parts as a
                # single JSON line, so a long search result or rendered
                # prompt easily blows past that and raises
                # LimitOverrunError mid-stream. Bump to 16 MiB.
                limit=16 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
            return

        assert proc.stdout is not None and proc.stderr is not None

        # Top-level cleanup: if the executor aborts iteration early
        # (fatal LogEvent detected, run cancelled, etc.) Python sends
        # GeneratorExit through ``aclose``. Without this finally the
        # subprocess would keep running. Inner exit paths set this flag
        # so cleanup is idempotent.
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

        # opencode logs upstream API errors (429, AI_APICallError,
        # maxRetriesExceeded, …) only to its own session log file under
        # ``~/.local/share/opencode/log/`` — not to stdout/stderr. Tail
        # that file and route ERROR lines through the same stderr queue
        # so the executor's central fatal-pattern detector terminates
        # the run instead of waiting for the per-run timeout.
        import time as _time

        _proc_start = _time.time()
        _opencode_log_dir = Path(
            os.environ.get(
                "OPENCODE_LOG_DIR",
                os.path.expanduser("~/.local/share/opencode/log"),
            )
        )

        async def _tail_opencode_log() -> None:
            # Wait briefly for the log file to appear (opencode creates
            # it within the first few hundred ms of startup).
            log_path: Path | None = None
            for _ in range(50):  # ~5s window
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
                out.append(LogEvent(run_id=run_id, level="warn", message=msg))
                if fatal is None:
                    fatal = detect_in_text_line(msg)
            return out, fatal

        stdout_chunks: list[str] = []
        streamed_text_parts: list[str] = []
        rate_limit_error: str | None = None

        # Persistent readline task so heartbeat timeouts don't drop bytes.
        # ``asyncio.wait_for`` would cancel the in-flight readline on every
        # heartbeat tick; racing against ``stderr_queue.get`` lets a log
        # tail entry (e.g. opencode's silent 429 retry log) flush the
        # queue immediately instead of after the 30s heartbeat tick.
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
                            level="info",
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
                        yield LogEvent(run_id=run_id, level="warn", message=msg)
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
                    if self._session_id is None:
                        sid = evt.get("sessionID")
                        if isinstance(sid, str) and sid:
                            self._session_id = sid
                    # Incrementally surface text/thinking parts so the UI
                    # gets live updates instead of waiting for the
                    # subprocess to exit.
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
            # Yield whatever events we captured before the timeout so the
            # conversation / transcript shows partial progress. Skip the
            # replay when streaming already surfaced them live.
            raw = "".join(stdout_chunks).strip()
            if raw and not streamed_text_parts:
                text_parts, thinking_parts, parsed_sid, _parse_failed = (
                    _parse_event_stream_with_thinking(raw)
                )
                if parsed_sid:
                    self._session_id = parsed_sid
                for tt in thinking_parts:
                    yield ThinkingEvent(run_id=run_id, text=tt)
                if text_parts:
                    yield TextEvent(run_id=run_id, text="".join(text_parts))
            for sl in stderr_lines:
                if sl.strip():
                    yield LogEvent(run_id=run_id, level="warn", message=sl)
            yield TimeoutEvent(
                run_id=run_id,
                timeout_seconds=timeout,
                error=f"timeout after {timeout}s",
            )
            yield DoneEvent(
                run_id=run_id,
                ok=False,
                error=f"timeout after {timeout}s",
                status="timeout",
            )
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
                yield LogEvent(run_id=run_id, level="warn", message=sl)

        raw = "".join(stdout_chunks).strip()
        if not raw:
            yield DoneEvent(
                run_id=run_id,
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                error="opencode produced no stdout" if proc.returncode != 0 else None,
            )
            return

        text_parts, thinking_parts, parsed_sid, parse_failed = (
            _parse_event_stream_with_thinking(raw)
        )
        if parsed_sid:
            self._session_id = parsed_sid
        if parse_failed and not text_parts:
            yield LogEvent(
                run_id=run_id,
                level="warn",
                message="opencode --format json output was not parseable; using raw stdout",
            )
            yield TextEvent(run_id=run_id, text=raw)
            yield DoneEvent(
                run_id=run_id,
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
            )
            return

        # Thinking events were emitted incrementally during streaming —
        # only replay them here if streaming didn't capture anything
        # (e.g. opencode buffered output and the loop saw nothing).
        if not streamed_text_parts:
            for thinking_text in thinking_parts:
                yield ThinkingEvent(run_id=run_id, text=thinking_text)

        # Strip markdown code fences so downstream consumers (validation,
        # webhooks, the UI) receive raw JSON instead of fenced blocks.
        # This consolidated event is what populates ``output_text`` in
        # the executor — the streamed delta events are UI-only.
        stripped_text = _strip_code_fences("".join(text_parts))
        yield TextEvent(run_id=run_id, text=stripped_text)
        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
        )


def _parse_event_stream_with_thinking(
    raw: str,
) -> tuple[list[str], list[str], str | None, bool]:
    """Parse opencode --format json output, extracting text and thinking parts.

    Returns (text_parts, thinking_parts, session_id, parse_failed).
    """
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    session_id: str | None = None
    any_json = False
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(evt, dict):
            continue
        any_json = True
        if session_id is None:
            sid = evt.get("sessionID")
            if isinstance(sid, str) and sid:
                session_id = sid
        if evt.get("type") == "text":
            part = evt.get("part")
            if isinstance(part, dict):
                ptype = part.get("type")
                text = part.get("text")
                if ptype == "text" and isinstance(text, str):
                    text_parts.append(text)
                elif ptype in ("thinking", "reasoning") and isinstance(text, str):
                    thinking_parts.append(text)
    return text_parts, thinking_parts, session_id, not any_json


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from model output.

    Models often wrap JSON in ```json blocks despite being told not to.
    This strips the outer fences so downstream validation and storage
    sees clean JSON (or plain text).
    """
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    return text
