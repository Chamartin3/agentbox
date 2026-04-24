"""Backend adapter for the OpenCode CLI runner.

Wraps ``agentbox.core.runners.opencode`` — ``render()`` builds
argv/env from the ``AgentDef``, ``run()`` delegates to the existing
subprocess loop.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.runners.opencode import (
    _parse_event_stream,
)

_NAME = "opencode"
_DEFAULT_OPENCODE_MODEL = "opencode-go/deepseek-v4-pro"


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
            stdin_data=stdin_data,
        ):
            yield ev

    @staticmethod
    async def _run_opencode(
        run_id: str,
        argv: list[str],
        cwd: Path,
        env: dict[str, str],
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
        timeout = 1200

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

        text_parts, _session_id, parse_failed = _parse_event_stream(raw)
        if parse_failed and not text_parts:
            yield LogEvent(
                run_id=run_id,
                level="warn",
                message="opencode --format json output was not parseable; using raw stdout",
            )
            yield DoneEvent(
                run_id=run_id,
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
            )
            return

        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
        )
