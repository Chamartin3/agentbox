"""Backend adapter for the OpenCode CLI runner.

Wraps ``agentbox.core.runners.opencode`` — ``render()`` builds
argv/env from the ``AgentDef``, ``run()`` delegates to the existing
subprocess loop.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    TimeoutEvent,
)
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.constants import DEFAULT_RUNNER_TIMEOUT_SECONDS
from agentbox.core.runners.opencode import (
    _DEFAULT_OPENCODE_MODEL,
    _parse_event_stream,
)

_NAME = "opencode"


class OpenCodeBackend:
    name = _NAME

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
    ) -> RenderedConfig:
        spec = agent.runner
        argv: list[str] = [
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--format",
            "json",
        ]

        argv += spec.extra_args

        if "--model" not in spec.extra_args and not spec.model:
            argv += ["--model", _DEFAULT_OPENCODE_MODEL]

        env = dict(os.environ)
        env["PWD"] = str(workdir)

        files: dict[Path, bytes] = {}
        composed_system = getattr(agent, "_composed_system", None)
        if composed_system is not None:
            files[Path("CLAUDE.md")] = composed_system.encode("utf-8")
        else:
            claude_md = workdir / "CLAUDE.md"
            if claude_md.exists():
                files[Path("CLAUDE.md")] = claude_md.read_bytes()

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            files=files,
            agent_meta={"timeout_seconds": spec.timeout_seconds},
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
            timeout=rendered.agent_meta.get("timeout_seconds", DEFAULT_RUNNER_TIMEOUT_SECONDS),
            stdin_data=stdin_data,
        ):
            yield ev

    @staticmethod
    async def _run_opencode(
        run_id: str,
        argv: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int = DEFAULT_RUNNER_TIMEOUT_SECONDS,
        stdin_data: bytes | None = None,
    ) -> AsyncIterator[RunEvent]:
        import asyncio
        import json

        from agentbox.core.runners._rate_limit import detect_in_opencode_event

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
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
        rate_limit_error: str | None = None

        try:
            async with asyncio.timeout(timeout):
                while True:
                    line_bytes = await proc.stdout.readline()
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
                    if isinstance(evt, dict):
                        detected = detect_in_opencode_event(evt)
                        if detected is not None:
                            rate_limit_error = detected
                            break
                await proc.wait()
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            stderr_task.cancel()
            # Yield whatever events we captured before the timeout so the
            # conversation / transcript shows partial progress.
            raw = "".join(stdout_chunks).strip()
            if raw:
                text_parts, thinking_parts, _session_id, _parse_failed = _parse_event_stream_with_thinking(raw)
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
            yield DoneEvent(run_id=run_id, ok=False, error=rate_limit_error)
            return

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

        text_parts, thinking_parts, _session_id, parse_failed = _parse_event_stream_with_thinking(raw)
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

        for thinking_text in thinking_parts:
            yield ThinkingEvent(run_id=run_id, text=thinking_text)

        # Strip markdown code fences so downstream consumers (validation,
        # webhooks, the UI) receive raw JSON instead of fenced blocks.
        stripped_text = _strip_code_fences("".join(text_parts))
        yield TextEvent(run_id=run_id, text=stripped_text)
        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
        )


def _parse_event_stream_with_thinking(raw: str) -> tuple[list[str], list[str], str | None, bool]:
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
