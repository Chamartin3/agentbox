"""Shared helpers for streaming a subprocess's stdout into RunEvents."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import DoneEvent, LogEvent, RunEvent


async def stream_subprocess(
    run_id: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 1200,
) -> AsyncIterator[RunEvent]:
    """Spawn `argv` in `cwd`, stream stdout as LogEvents, emit a DoneEvent."""
    process_env = dict(os.environ)
    if env:
        process_env.update(env)

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=process_env,
        )
    except FileNotFoundError as exc:
        yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
        return

    assert proc.stdout is not None

    async def _read() -> AsyncIterator[RunEvent]:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield LogEvent(
                run_id=run_id, message=line.decode(errors="replace").rstrip()
            )

    try:
        async with asyncio.timeout(timeout):
            async for ev in _read():
                yield ev
            await proc.wait()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        yield DoneEvent(run_id=run_id, ok=False, error=f"timeout after {timeout}s")
        return

    yield DoneEvent(run_id=run_id, ok=proc.returncode == 0, exit_code=proc.returncode)
