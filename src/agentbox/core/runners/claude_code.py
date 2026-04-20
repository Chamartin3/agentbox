"""Generic Claude Code CLI runner.

Project-agnostic: config paths, MCP servers, allowed tools, and agent
JSON come from the AgentDef.RunnerSpec.

The runner invokes `claude --output-format json`, which emits a single
JSON envelope on completion. We parse it into structured events:
  - `result` (string) → TextEvent
  - `usage` + `total_cost_usd` → UsageEvent
  - non-zero exit / `is_error` → DoneEvent(ok=False)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.constants import RunnerKind
from agentbox.core.runners.base import Runner, RunRequest
from agentbox.core.workspaces import (
    claude_agents_path,
    claude_settings_path,
    load_capabilities,
)


_FILENAME_SAFE = str.maketrans({"/": "_", "\\": "_", ":": "_"})


def _materialize_agents(agents_json_path: Path, target_dir: Path) -> None:
    """Write each entry in ``claude_agents.json`` as a `.claude/agents/*.md`
    file so Claude Code can discover them via its built-in lookup.

    Avoids `--agents <huge-json>` (single argv arg > MAX_ARG_STRLEN → E2BIG).

    JSON shape: ``{<agent_name>: {description, prompt, allowedTools}}``.
    """
    try:
        data = json.loads(agents_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in target_dir.glob("*.md"):
        stale.unlink()

    for name, spec in data.items():
        if not isinstance(spec, dict):
            continue
        description = str(spec.get("description", "")).replace('"', '\\"')
        tools = spec.get("allowedTools") or []
        prompt = str(spec.get("prompt", ""))
        lines = ["---", f"name: {name}", f'description: "{description}"']
        if tools:
            lines.append(f"tools: {', '.join(tools)}")
        lines.extend(["---", "", prompt])
        filename = name.translate(_FILENAME_SAFE) + ".md"
        (target_dir / filename).write_text("\n".join(lines), encoding="utf-8")


def _intersect_allowed_tools(
    agent_tools: list[str], workspace_tools: list[str] | None
) -> list[str]:
    """Effective allow list = agent ∩ workspace.

    If either side is empty/None, treat it as "no restriction" so the
    other side governs alone. This matches the user-facing intuition:
    leaving a list blank means "don't restrict here".
    """
    if not agent_tools and not workspace_tools:
        return []
    if not agent_tools:
        return list(workspace_tools or [])
    if not workspace_tools:
        return list(agent_tools)
    ws_set = set(workspace_tools)
    return [t for t in agent_tools if t in ws_set]


class ClaudeCodeRunner(Runner):
    kind = RunnerKind.CLAUDE_CODE

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        if shutil.which("claude") is None:
            yield DoneEvent(run_id=req.run_id, ok=False, error="claude CLI not found")
            return

        spec = req.agent.runner
        # Prompt is piped via stdin (not argv) to avoid "Argument list too
        # long" (E2BIG) when the composed prompt exceeds ARG_MAX. The
        # `-p` flag makes claude read from stdin when no positional
        # prompt argument is given.
        argv: list[str] = ["claude", "-p"]

        if spec.model:
            argv += ["--model", spec.model]

        capabilities = load_capabilities(req.workdir)
        ws_mcp = capabilities.get("mcp_config_path")
        mcp_config = ws_mcp if ws_mcp else spec.mcp_config_path
        if mcp_config:
            argv += [
                "--mcp-config",
                str(req.project_root / mcp_config),
                "--strict-mcp-config",
            ]

        settings_file = claude_settings_path(req.workdir)
        agents_file = claude_agents_path(req.workdir)
        if settings_file.exists():
            argv += ["--settings", str(settings_file)]
        if agents_file.exists():
            _materialize_agents(agents_file, req.workdir / ".claude" / "agents")

        effective_tools = _intersect_allowed_tools(
            spec.allowed_tools, capabilities.get("allowed_tools")
        )
        if effective_tools:
            argv += ["--allowedTools", *effective_tools]

        argv += ["--output-format", "json", "--permission-mode", "bypassPermissions"]
        argv += spec.extra_args

        yield LogEvent(
            run_id=req.run_id,
            message=f"$ claude -p ... (model={spec.model or 'default'})",
        )

        # Strip Anthropic API auth so the CLI uses its own subscription
        # OAuth instead of the parent process's API key.
        env = dict(os.environ)
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)

        async for ev in _run_claude(
            req.run_id,
            argv,
            req.workdir,
            env,
            spec.timeout_seconds,
            stdin_data=req.input.encode("utf-8"),
        ):
            yield ev


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
            error="claude produced no stdout" if proc.returncode != 0 else None,
        )
        return

    envelope = _parse_envelope(raw)
    if envelope is None:
        # Fall back to streaming raw stdout as log lines so we don't
        # lose output on an unexpected CLI format.
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
