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
import contextlib
import json
import os
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
    TextEvent,
    TimeoutEvent,
    UsageEvent,
)
from agentbox.core.constants import RunnerKind, SessionMode
from agentbox.core.streaming.rate_limit import detect_in_opencode_event
from agentbox.core.runners.base import Runner, RunRequest
from agentbox.core.workspaces import opencode_config_path

_DEFAULT_OPENCODE_MODEL = "opencode/deepseek-v4-flash-free"

# Built-in opencode tools that must be disabled for headless one-shot agents.
# Headless agents are pure JSON-emitters: they MUST NOT read, write, edit, or
# shell out — they answer in their reply message, full stop.
_HEADLESS_DISABLED_TOOLS = (
    "bash",
    "edit",
    "patch",
    "read",
    "write",
    "glob",
    "grep",
    "list",
    "webfetch",
    "websearch",
    "todoread",
    "todowrite",
    "task",
)


class OpenCodeRunner(Runner):
    kind = RunnerKind.OPENCODE
    conversation_format = "opencode-session"

    def __init__(self) -> None:
        super().__init__()
        # Per-run instance state. The executor constructs a fresh
        # OpenCodeRunner per run via _try_backend → cls(), so cross-run
        # leakage isn't possible today; if anyone starts reusing
        # instances they must reset this between runs.
        self._session_id: str | None = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return self._session_id

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
        target = req.workdir / "opencode.json"
        if ws_config.exists():
            try:
                target.write_bytes(ws_config.read_bytes())
            except OSError as exc:
                yield LogEvent(
                    run_id=req.run_id,
                    level="warn",
                    message=f"failed to stage opencode.json into workdir: {exc}",
                )

        # Headless agents get every tool disabled — they answer in their
        # reply message, never via file writes or shell commands. Patch
        # the staged opencode.json to add a locked-down agent entry and
        # pass --agent so opencode uses it.
        if req.agent.session_mode == SessionMode.HEADLESS:
            try:
                _harden_opencode_config_for_headless(target, req.agent.id)
            except OSError as exc:
                yield LogEvent(
                    run_id=req.run_id,
                    level="warn",
                    message=f"failed to harden opencode.json for headless: {exc}",
                )
            if "--agent" not in spec.extra_args:
                argv += ["--agent", req.agent.id]

        # Extra args from the agent definition (e.g. --agent, --model).
        argv += spec.extra_args

        # Inject a default ``--model`` if neither the agent's runner spec
        # nor extra_args already pin one. Without this, opencode falls back
        # to its built-in default (zen-free), which is aggressively
        # rate-limited and causes spurious 429 failures.
        if "--model" not in spec.extra_args and not spec.model:
            argv += ["--model", _DEFAULT_OPENCODE_MODEL]

        # Message is piped via stdin instead of a positional arg to avoid
        # "Argument list too long" (E2BIG) for large prompts.
        stdin_data = req.input.encode("utf-8")

        # Register the model up-front so it's persisted even if the run
        # fails before opencode emits its usage summary (rate-limit kill,
        # timeout, parse failure, missing sessionID, etc.). The real
        # UsageEvent at the end will add token counts; the model column
        # is preserved by COALESCE in record_usage. Resolution order:
        #   1. spec.model
        #   2. value following ``--model`` in extra_args
        #   3. _DEFAULT_OPENCODE_MODEL (matches the inject above)
        # We must guarantee a non-empty model — otherwise runs that fail
        # to capture a sessionID end up with no usage row at all.
        early_model = spec.model
        if not early_model and "--model" in spec.extra_args:
            idx = spec.extra_args.index("--model")
            if idx + 1 < len(spec.extra_args):
                early_model = spec.extra_args[idx + 1]
        if not early_model:
            early_model = _DEFAULT_OPENCODE_MODEL
        yield UsageEvent(run_id=req.run_id, model=early_model)

        yield LogEvent(
            run_id=req.run_id, message=f"$ opencode run --stdin ... (cwd={req.workdir})"
        )

        async for ev in self._run_opencode(
            req.run_id, argv, req.workdir, spec.timeout_seconds, stdin_data=stdin_data
        ):
            yield ev

    async def _run_opencode(
        self,
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
                # See backends/opencode.py — default 64 KiB readline limit
                # truncates large opencode tool_result / message JSON lines
                # and raises LimitOverrunError.
                limit=16 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            yield DoneEvent(run_id=run_id, ok=False, error=str(exc))
            return

        assert proc.stdout is not None and proc.stderr is not None

        # Stream stdout line-by-line so we can fail fast on rate-limit /
        # auth errors instead of waiting for ``timeout_seconds``. Opencode
        # retries 429s internally and only emits the final error event
        # when it gives up, so we still have to inspect each event — but
        # at least we don't block on ``communicate()``.
        if stdin_data is not None and proc.stdin is not None:
            try:
                proc.stdin.write(stdin_data)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                # The child exited before we could send the prompt
                # (e.g. immediate auth/credit failure). Continue and let
                # the stdout reader surface the error event.
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

        text_parts, session_id, parse_failed = _parse_event_stream(raw)
        if session_id:
            self._session_id = session_id
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
        # Strip markdown fences so downstream validation sees clean JSON.
        full_text = _strip_code_fences("".join(text_parts))
        yield TextEvent(run_id=run_id, text=full_text)

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
        else:
            # No sessionID emitted in the stream — we can't fetch usage
            # at all. Surface this loudly so it doesn't silently produce
            # runs with no token counts (the early UsageEvent above still
            # registers the model, but tokens/cost will be missing).
            yield LogEvent(
                run_id=run_id,
                level="warn",
                message="opencode stream emitted no sessionID; token/cost data unavailable",
            )

        yield DoneEvent(
            run_id=run_id,
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
        )


def _harden_opencode_config_for_headless(target: Path, agent_id: str) -> None:
    """Lock down ``opencode.json`` so a headless agent has zero tools.

    Adds (or overwrites) an entry for ``agent_id`` with every built-in
    tool flipped off and a deny-all permission policy. Also flips the
    same tools off in any other enabled agent entry — defensive: with
    ``--dangerously-skip-permissions`` set, opencode would otherwise
    fall back to a different agent's tool list on lookup miss.
    """
    if not target.is_file():
        cfg: dict = {}
    else:
        try:
            cfg = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cfg = {}

    disabled_tools = dict.fromkeys(_HEADLESS_DISABLED_TOOLS, False)
    deny_all = dict.fromkeys(_HEADLESS_DISABLED_TOOLS, "deny")
    deny_all["*"] = "deny"

    agents = cfg.setdefault("agent", {})
    agents[agent_id] = {
        "description": f"Headless one-shot run of {agent_id} (tools disabled)",
        "tools": dict(disabled_tools),
        "permission": dict(deny_all),
    }

    # Belt-and-braces: also blank tools on the other enabled agents so a
    # stray fallback can't grant filesystem access.
    for name, entry in list(agents.items()):
        if name == agent_id or not isinstance(entry, dict):
            continue
        if entry.get("disable"):
            continue
        existing_tools = entry.get("tools") if isinstance(entry.get("tools"), dict) else {}
        entry["tools"] = {**existing_tools, **disabled_tools}

    # Global permission deny-all (with --dangerously-skip-permissions
    # this is best-effort but keeps things sane if that flag changes).
    cfg.setdefault("permission", {})
    if isinstance(cfg["permission"], dict):
        cfg["permission"].update(deny_all)

    target.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


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


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from model output."""
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    return text
