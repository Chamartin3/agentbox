"""Backend adapter for the Claude Code CLI.

Self-contained after Plan 16 Phase 4: previously delegated to
``agentbox.core.runners.claude_code._run_claude``; that subprocess loop
and its helpers now live inline below.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    TimeoutEvent,
    UsageEvent,
)
from agentbox.core.agent.config import RuntimeConfig
from agentbox.core.run.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.run.streaming.rate_limit import detect_in_text_line
from agentbox.core.workspace.manager import load_capabilities

_NAME = "claude_code"

# Heartbeat cadence — without this, a stuck ``claude`` emits zero events
# between launch and the hard timeout because ``--output-format json``
# only flushes its envelope at exit.
_HEARTBEAT_INTERVAL_SECONDS = 30.0


class ClaudeCodeBackend(BackendAdapter):
    name = _NAME
    conversation_format: str | None = "claude-cli-jsonl"

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
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
        runner_config: Any | None = None,
    ) -> RenderedConfig:
        runtime_cfg = RuntimeConfig.from_agent(agent)
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

        argv += [
            "--mcp-config",
            "claude_mcp.json",
            "--strict-mcp-config",
            "--settings",
            "claude_settings.json",
        ]

        capabilities = load_capabilities(workdir)
        effective_tools = _intersect_allowed_tools(
            list(runtime_cfg.allowed_tools), capabilities.get("allowed_tools")
        )
        if effective_tools:
            argv += ["--allowedTools", *effective_tools]

        argv += ["--output-format", "json", "--permission-mode", "bypassPermissions"]
        argv += extra_args

        env = dict(os.environ)
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)

        timeout_seconds = agent_runner.timeout_seconds

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
            rendered.agent_meta["timeout_seconds"],
            stdin_data=input.encode("utf-8"),
        ):
            yield ev


# ---------------------------------------------------------------------------
# Inlined subprocess loop (formerly runners/claude_code.py:_run_claude)
# ---------------------------------------------------------------------------


def _intersect_allowed_tools(
    agent_tools: list[str], workspace_tools: list[str] | None
) -> list[str]:
    """Effective allow list = agent ∩ workspace.

    If either side is empty/None, treat it as "no restriction" so the
    other side governs alone.
    """
    if not agent_tools and not workspace_tools:
        return []
    if not agent_tools:
        return list(workspace_tools or [])
    if not workspace_tools:
        return list(agent_tools)
    ws_set = set(workspace_tools)
    return [t for t in agent_tools if t in ws_set]


def _kill_group(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pid, sig)


async def _run_claude(
    run_id: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: int,
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
                        level="info",
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
            run_id=run_id, timeout_seconds=timeout, error=f"timeout after {timeout}s"
        )
        yield DoneEvent(
            run_id=run_id, ok=False, error=f"timeout after {timeout}s", status="timeout"
        )
        return

    with contextlib.suppress(asyncio.CancelledError):
        await stderr_task

    if rate_limit_error is not None:
        for sl in stderr_lines:
            if sl.strip():
                yield LogEvent(run_id=run_id, level="warn", message=sl)
        yield DoneEvent(run_id=run_id, ok=False, error=rate_limit_error)
        return

    for sl in stderr_lines:
        if sl.strip():
            yield LogEvent(run_id=run_id, level="warn", message=sl)

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


def _parse_envelope(raw: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of claude's stdout."""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    start = raw.find("{")
    if start < 0:
        return None
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError:
        return None


def _build_usage_event(run_id: str, envelope: dict[str, Any]) -> UsageEvent | None:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        return None
    model_usage = envelope.get("modelUsage")
    model_name: str | None = None
    if isinstance(model_usage, dict) and model_usage:
        model_name = next(iter(model_usage.keys()), None)
    return UsageEvent(
        run_id=run_id,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cost_usd=_safe_float(envelope.get("total_cost_usd")),
        model=model_name,
    )


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
