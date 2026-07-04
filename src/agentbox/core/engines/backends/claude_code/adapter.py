"""Backend adapter for the Claude Code CLI."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.constants import LogLevel, RunStatus
from agentbox.core.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    TimeoutEvent,
)
from agentbox.core.engines.contracts.base import BackendAdapter, RenderedConfig
from agentbox.core.engines.backends.claude_code.render import (
    _runtime_config_view_from_agent,
)
from agentbox.core.engines.backends.claude_code.tools import (
    NATIVE_TOOLS as _CLAUDE_TOOLS,
)
from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.translation import (
    intersect_allowed_tools,
    translate_tool,
)
from agentbox.core.engines.backends.claude_code.views import (
    _build_usage_event,
    _parse_envelope,
)
from agentbox.core.engines.streaming.rate_limit import detect_in_text_line

_NAME = "claude_code"

# Heartbeat cadence — without this, a stuck ``claude`` emits zero events
# between launch and the hard timeout because ``--output-format json``
# only flushes its envelope at exit.
_HEARTBEAT_INTERVAL_SECONDS = 30.0


class ClaudeCodeBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "claude-cli-jsonl"

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return transcript_path

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
        if runtime_config is None:
            runtime_config = _runtime_config_view_from_agent(agent)

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
        argv: list[str] = ["claude", "-p"]

        if model:
            argv += ["--model", model]

        # Native MCP config in the run cwd. Permissions are bypassed at
        # dispatch (--permission-mode bypassPermissions) and tools are gated
        # via --allowedTools, so no settings file is needed.
        argv += [
            "--mcp-config",
            ".mcp.json",
            "--strict-mcp-config",
        ]

        effective_tools = intersect_allowed_tools(
            set(runtime_config.allowed_tools),
            ws_allowed_tools,
        )
        if effective_tools:
            native_tools = [translate_tool(t, _CLAUDE_TOOLS) for t in effective_tools]
            argv += ["--allowedTools", *native_tools]

        argv += ["--output-format", "json", "--permission-mode", "bypassPermissions"]
        argv += extra_args

        env = dict(os.environ)
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)

        timeout_seconds = getattr(agent_runner, "timeout_seconds", None)

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            agent_meta={"timeout_seconds": timeout_seconds},
            model=model,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        if shutil.which("claude") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="claude CLI not found")
            return

        yield LogEvent(
            run_id=run_id,
            message=f"$ claude -p ... (cwd={rendered.cwd})",
        )

        async for ev in _run_claude(
            run_id,
            list(rendered.argv),
            rendered.cwd,
            dict(rendered.env),
            rendered.agent_meta.get("timeout_seconds"),
            stdin_data=input.encode("utf-8"),
        ):
            yield ev


def _kill_group(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pid, sig)


async def _run_claude(
    run_id: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int | None,
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
            start_new_session=True,
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
    rate_limit_error: str | None = None

    async def _watch_stderr() -> None:
        nonlocal rate_limit_error
        assert proc.stderr is not None
        while True:
            line_bytes = await proc.stderr.readline()
            if not line_bytes:
                return
            text = line_bytes.decode(errors="replace").rstrip()
            stderr_lines.append(text)
            if rate_limit_error is None:
                detected = detect_in_text_line(text)
                if detected is not None:
                    rate_limit_error = detected
                    _kill_group(proc.pid, signal.SIGKILL)
                    return

    stderr_task = asyncio.create_task(_watch_stderr())
    stdout_task: asyncio.Task[bytes] = asyncio.create_task(proc.stdout.read())
    wait_task: asyncio.Task[int] = asyncio.create_task(proc.wait())

    try:
        async with asyncio.timeout(timeout):
            elapsed = 0
            while not wait_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(wait_task),
                        _HEARTBEAT_INTERVAL_SECONDS,
                    )
                except TimeoutError:
                    elapsed += int(_HEARTBEAT_INTERVAL_SECONDS)
                    yield LogEvent(
                        run_id=run_id,
                        level=LogLevel.INFO,
                        message=(
                            f"claude silent for {elapsed}s "
                            f"(pid={proc.pid}); still waiting for child to exit"
                        ),
                    )
                    continue
            _kill_group(proc.pid, signal.SIGTERM)
            stdout = await stdout_task
    except TimeoutError:
        _kill_group(proc.pid, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        stdout_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await stdout_task
        wait_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await wait_task
        stderr_task.cancel()
        yield TimeoutEvent(
            run_id=run_id, timeout_seconds=timeout or 0, error=f"timeout after {timeout}s"
        )
        yield DoneEvent(
            run_id=run_id, ok=False, error=f"timeout after {timeout}s", status=RunStatus.TIMEOUT
        )
        return

    with contextlib.suppress(asyncio.CancelledError):
        await stderr_task

    if rate_limit_error is not None:
        for sl in stderr_lines:
            if sl.strip():
                yield LogEvent(run_id=run_id, level=LogLevel.WARN, message=sl)
        yield DoneEvent(run_id=run_id, ok=False, error=rate_limit_error)
        return

    for sl in stderr_lines:
        if sl.strip():
            yield LogEvent(run_id=run_id, level=LogLevel.WARN, message=sl)

    raw = stdout.decode(errors="replace").strip()
    if not raw:
        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            error="claude produced no stdout" if proc.returncode != 0 else None,
        )
        return

    envelope = _parse_envelope(raw)
    if envelope is None:
        for line in raw.splitlines():
            yield LogEvent(run_id=run_id, message=line.rstrip())
        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
        )
        return

    text = envelope.get("result")
    if isinstance(text, str) and text:
        yield TextEvent(run_id=run_id, text=text)

    usage = _build_usage_event(run_id, envelope)
    if usage is not None:
        yield usage

    is_error = bool(envelope.get("is_error", False))
    api_error = envelope.get("api_error_status")
    error_msg = envelope.get("error")
    ok = proc.returncode == 0 and not is_error and not api_error
    err: str | None = None
    if not ok:
        if isinstance(error_msg, str) and error_msg:
            err = error_msg
        elif api_error:
            err = f"api_error_status={api_error}"
        elif is_error:
            err = "claude reported is_error=true"
        elif proc.returncode != 0:
            err = f"claude exited {proc.returncode}"
    yield DoneEvent(
        run_id=run_id,
        ok=ok,
        exit_code=proc.returncode,
        error=err,
    )


__all__ = ["ClaudeCodeBackend", "_run_claude"]
