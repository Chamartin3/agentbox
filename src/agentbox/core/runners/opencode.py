"""OpenCode CLI runner — headless execution via ``opencode run``.

Invocation shape::

    opencode run --format json --dangerously-skip-permissions [extra_args] <message>

Runs with ``--format json`` so we can capture the sessionID and
concatenate the assistant's ``text`` parts into the final output. After
the process exits we shell out to ``opencode export <sessionID>`` to
pull model id + token usage + cost off the session record (the streamed
JSON events don't include a usage summary). The concatenated text is
yielded as a single ``TextEvent`` so the existing post-processor — which
extracts JSON from the model's raw text — keeps working unchanged.

Usage info (``--agent``, ``--model``, etc.) is passed through extra_args
in the agent definition.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.constants import RunnerKind
from agentbox.core.runners.base import Runner, RunRequest
from agentbox.core.workspaces import opencode_config_path


class OpenCodeRunner(Runner):
    kind = RunnerKind.OPENCODE

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        if shutil.which("opencode") is None:
            yield DoneEvent(run_id=req.run_id, ok=False, error="opencode CLI not found")
            return

        spec = req.agent.runner
        # ``--dangerously-skip-permissions`` is required for headless runs:
        # opencode's default permission policy is "ask", and the CLI has
        # no way to answer prompts when invoked via ``run``, so any tool
        # call would deadlock and the model returns empty output.
        # ``--format json`` streams structured events on stdout — we
        # extract the assistant's text parts and the sessionID from them.
        argv: list[str] = [
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--format",
            "json",
        ]

        # Use workspace-generated config if available. The opencode CLI
        # auto-discovers an `opencode.json` in cwd; it has no `--config`
        # flag in current versions. Copy the generated config into the
        # workdir so opencode picks it up.
        ws_config = opencode_config_path(req.workdir)
        if ws_config.exists():
            target = req.workdir / "opencode.json"
            try:
                target.write_bytes(ws_config.read_bytes())
            except OSError as exc:
                yield LogEvent(
                    run_id=req.run_id,
                    level="warn",
                    message=f"failed to stage opencode.json into workdir: {exc}",
                )

        # Extra args from the agent definition (e.g. --agent, --model).
        argv += spec.extra_args

        # Message is piped via stdin instead of a positional arg to avoid
        # "Argument list too long" (E2BIG) for large prompts.
        stdin_data = req.input.encode("utf-8")

        yield LogEvent(run_id=req.run_id, message=f"$ opencode run --stdin ... (cwd={req.workdir})")

        async for ev in self._run_opencode(
            req.run_id, argv, req.workdir, spec.timeout_seconds, stdin_data=stdin_data
        ):
            yield ev

    @staticmethod
    async def _run_opencode(
        run_id: str,
        argv: list[str],
        cwd: Path,
        timeout: int,
        stdin_data: bytes | None = None,
    ) -> AsyncIterator[RunEvent]:
        """Spawn opencode with --format json, parse events, yield Text/Usage/Done."""
        env = dict(os.environ)
        # opencode resolves its "project directory" from the PWD env var,
        # not getcwd(). Without this override, opencode inherits PWD from
        # the parent agentbox process and binds the workspace's
        # opencode.json to the wrong project — agent definitions become
        # invisible.
        env["PWD"] = str(cwd)

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

        try:
            async with asyncio.timeout(timeout):
                stdout, stderr = await proc.communicate(input=stdin_data)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            yield DoneEvent(run_id=run_id, ok=False, error=f"timeout after {timeout}s")
            return

        if stderr:
            for line in stderr.decode(errors="replace").splitlines():
                if line.strip():
                    yield LogEvent(run_id=run_id, level="warn", message=line.rstrip())

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            yield DoneEvent(
                run_id=run_id,
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                error="opencode produced no stdout" if proc.returncode != 0 else None,
            )
            return

        text_parts, session_id, parse_failed = _parse_event_stream(raw)
        if parse_failed and not text_parts:
            # Stream wasn't JSONL — fall back to treating stdout as raw text
            # so we don't lose output on an opencode CLI version change.
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

        # Yield the assistant text as TextEvent. The executor collects
        # TextEvent.text into the run output, which the webhook post-processor
        # validates against the Pydantic schema and persists.
        yield TextEvent(run_id=run_id, text="".join(text_parts))

        # Fetch session metadata (model, tokens, cost) via `opencode export`.
        # Best-effort: the run itself succeeded even if export fails.
        if session_id:
            usage = await _fetch_session_usage(run_id, session_id, cwd, env)
            if usage is not None:
                yield usage
            else:
                yield LogEvent(
                    run_id=run_id,
                    level="warn",
                    message=f"opencode export {session_id} returned no usage info",
                )

        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
        )


def _parse_event_stream(raw: str) -> tuple[list[str], str | None, bool]:
    """Parse opencode --format json output.

    Returns (text_parts, session_id, parse_failed). ``text_parts`` are the
    assistant's ``text`` part contents in stream order (reasoning/tool
    parts are ignored). ``parse_failed`` is True when no line decoded as
    JSON — the caller falls back to raw stdout in that case.
    """
    text_parts: list[str] = []
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
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
    return text_parts, session_id, not any_json


async def _fetch_session_usage(
    run_id: str,
    session_id: str,
    cwd: Path,
    env: dict[str, str],
) -> UsageEvent | None:
    """Call ``opencode export <session_id>`` to pull model + token usage."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencode",
            "export",
            session_id,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        return None

    try:
        async with asyncio.timeout(15):
            stdout, _stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return None

    if proc.returncode != 0:
        return None

    raw = stdout.decode(errors="replace")
    # `opencode export` prefixes with a banner line ("Exporting session: …")
    # before the JSON body, so locate the first '{'.
    start = raw.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(raw[start:])
    except json.JSONDecodeError:
        return None

    info = data.get("info") if isinstance(data, dict) else None
    if not isinstance(info, dict):
        return None

    model: str | None = None
    model_info = info.get("model")
    if isinstance(model_info, dict):
        provider = model_info.get("providerID")
        mid = model_info.get("id")
        if mid:
            model = f"{provider}/{mid}" if provider else str(mid)

    tokens = info.get("tokens") if isinstance(info.get("tokens"), dict) else {}
    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    cost = info.get("cost")
    try:
        cost_f = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_f = None

    return UsageEvent(
        run_id=run_id,
        input_tokens=int(tokens.get("input") or 0),
        output_tokens=int(tokens.get("output") or 0),
        cache_read_tokens=int(cache.get("read") or 0),
        cache_write_tokens=int(cache.get("write") or 0),
        cost_usd=cost_f,
        model=model,
    )


