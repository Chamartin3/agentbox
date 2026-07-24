"""Backend adapter for the OpenAI Codex CLI (``codex exec --json``).

Streaming uses the shared
:func:`agentbox.core.engines.backends.streaming.jsonl.stream_jsonl_subprocess` helper.
"""

from __future__ import annotations

from agentbox.core.data.jsontypes import RawJson

import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.data.events import DoneEvent, LogEvent, RunEvent, TextEvent, UsageEvent
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.engines.backends.credenv import build_run_env
from agentbox.core.data import RenderedConfig
from agentbox.core.data.workenv import Item
from agentbox.core.data.constants import AGENT_TOOLS_SERVER_NAME, HOST_ENV_SERVER_NAME
from agentbox.core.data.payload_types import McpStdioServerSpec
from agentbox.core.engines.backends.codex.mcp import (
    build_codex_intrinsic_mcp_argv,
    mcp_flags_from_agent_meta,
)
from agentbox.core.tools.mcp_servers.specs import (
    agent_tools_server_spec,
    host_env_server_spec,
)
from agentbox.core.engines.backends.codex.render import build_codex_items
from agentbox.core.engines.backends.codex.tools import NATIVE_TOOLS as _CODEX_TOOLS
from agentbox.core.engines.backends.streaming.jsonl import stream_jsonl_subprocess
from agentbox.core.data import CanonicalTool
from agentbox.core.tools.translation import (
    intersect_allowed_tools,
    translate_tool,
)

_NAME = "codex"


def build_codex_argv(
    model: str | None, extra_args: list[str] | None, default_model: str | None
) -> list[str]:
    """Construct the codex argv. Public so tests can introspect it."""
    args = list(extra_args or [])
    effective_model = model or default_model
    argv: list[str] = ["codex", "exec", "--json"]
    if effective_model and "--model" not in args:
        argv += ["--model", effective_model]
    argv += args
    return argv


def parse_codex_event(
    evt: RawJson, run_id: str
) -> tuple[list[RunEvent], str | None]:
    """Parse one ``codex exec --json`` event line.

    Codex's JSON schema isn't strictly stable across versions. We accept
    the common shapes seen in the wild:

      - ``{"type":"thread.started","thread_id":"..."}``
      - ``{"type":"item.completed","item":{"item_type":"assistant_message","text":"..."}}``
      - ``{"type":"turn.completed","usage":{"input_tokens":...,"output_tokens":...}}``

    Unknown event types are ignored.
    """
    events: list[RunEvent] = []
    session_id: str | None = None

    etype = evt.get("type")
    if etype in ("thread.started", "session.started", "session"):
        sid = evt.get("thread_id") or evt.get("session_id") or evt.get("id")
        if isinstance(sid, str) and sid:
            session_id = sid

    item = evt.get("item")
    if isinstance(item, dict):
        item_type = item.get("item_type") or item.get("type")
        text = item.get("text")
        if (
            item_type in ("assistant_message", "agent_message", "message")
            and isinstance(text, str)
            and text
        ):
            events.append(TextEvent(run_id=run_id, text=text, delta=True))

    # Alternate shape: top-level "delta" or "text"
    delta = evt.get("delta")
    if isinstance(delta, dict):
        t = delta.get("text") or delta.get("content")
        if isinstance(t, str) and t:
            events.append(TextEvent(run_id=run_id, text=t, delta=True))

    usage = evt.get("usage")
    if isinstance(usage, dict):
        _m = evt.get("model")
        model = _m if isinstance(_m, str) else None
        events.append(
            UsageEvent(
                run_id=run_id,
                model=model,
                input_tokens=_int_or_zero(usage.get("input_tokens")),
                output_tokens=_int_or_zero(usage.get("output_tokens")),
                cache_read_tokens=_int_or_zero(usage.get("cached_input_tokens")),
            )
        )

    return events, session_id


def _int_or_zero(v: object) -> int:
    if not isinstance(v, (int, float, str, bytes)):
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class CodexBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "codex-session"
    supports_mcp: ClassVar[bool] = False  # codex has no native MCP support today
    NATIVE_TOOLS = _CODEX_TOOLS  # noqa: N815 — canonical-tool → codex-name mapping

    def __init__(self) -> None:
        self._session_id: str | None = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return self._session_id

    def build_workspace_items(self, config: Any) -> list[Item]:
        return build_codex_items(config)

    def declared_tools(self) -> list[CanonicalTool]:
        return list(_CODEX_TOOLS.keys())

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
        ws_allowed_tools: set[CanonicalTool] | None = None,
        **kwargs: Any,
    ) -> RenderedConfig:
        agent_runner = getattr(agent, "runner", None)
        # No terminal fallback: the runner profile supplies the model, else the
        # codex CLI picks its own default (model=None).
        model = getattr(runner_config, "model", None)
        extra_args = list(getattr(runner_config, "extra_args", None) or [])

        argv = build_codex_argv(model, extra_args, None)

        if runtime_config is not None:
            effective_tools = intersect_allowed_tools(
                set(runtime_config.allowed_tools),
                ws_allowed_tools,
            )
            if effective_tools:
                native_tools = [translate_tool(t, _CODEX_TOOLS) for t in effective_tools]
                argv += ["--allowedTools", *native_tools]

        env = build_run_env(creds)

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
        if shutil.which("codex") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="codex CLI not found")
            return

        # Inject MCP server config flags derived from the executor-resolved
        # external_mcp_servers stored in agent_meta.  Codex has no per-server
        # allow-list, so we only emit the server coordinates here; canonical-
        # tool scoping is handled by --allowedTools (set during render).
        mcp_flags = mcp_flags_from_agent_meta(rendered.agent_meta)

        # Re-resolve intrinsic MCP servers (host_env, agent_tools) from the
        # raw grant inputs stored in agent_meta by the executor, matching the
        # token backend's Option-B re-resolution pattern.  The server specs are
        # converted to -c TOML flags, and their env vars are merged into the
        # codex subprocess environment so that the spawned server processes
        # inherit the grant context.
        intrinsic_env: dict[str, str] = {}
        intrinsic_specs: dict[str, McpStdioServerSpec] = {}
        _host_env_grants = rendered.agent_meta.get("host_env_grants")
        if _host_env_grants:
            _he_spec = host_env_server_spec(
                grants=_host_env_grants,
                workspace_id=rendered.agent_meta.get("host_env_workspace_id") or "",
                workdir=Path(rendered.agent_meta.get("host_env_workdir") or "."),
                db_path=Path(
                    rendered.agent_meta.get("host_env_db_path") or "/data/agentbox.sqlite"
                ),
            )
            intrinsic_specs[HOST_ENV_SERVER_NAME] = _he_spec
            intrinsic_env.update(_he_spec["env"])

        _agent_tool_grants_raw = rendered.agent_meta.get("agent_tool_grants")
        _agent_id = rendered.agent_meta.get("agent_id")
        if _agent_tool_grants_raw and _agent_id:
            _at_grants: set[str] = set(_agent_tool_grants_raw)
            _at_spec = agent_tools_server_spec(
                grants=_at_grants,
                agent_id=_agent_id,
                workdir=Path(rendered.agent_meta.get("host_env_workdir") or "."),
                db_path=Path(
                    rendered.agent_meta.get("host_env_db_path") or "/data/agentbox.sqlite"
                ),
            )
            intrinsic_specs[AGENT_TOOLS_SERVER_NAME] = _at_spec
            intrinsic_env.update(_at_spec["env"])

        if intrinsic_specs:
            mcp_flags += build_codex_intrinsic_mcp_argv(intrinsic_specs)

        argv = list(rendered.argv) + mcp_flags

        yield LogEvent(
            run_id=run_id,
            message=f"$ {' '.join(argv)} (cwd={rendered.cwd})",
        )

        timeout = rendered.agent_meta.get("timeout_seconds")

        # Merge intrinsic server env vars into the subprocess environment so
        # that codex can pass them to the MCP server subprocesses it spawns.
        subprocess_env = {**dict(rendered.env), **intrinsic_env}

        async for ev, sid in stream_jsonl_subprocess(
            run_id=run_id,
            argv=argv,
            cwd=rendered.cwd,
            env=subprocess_env,
            timeout=timeout,
            parse_event=parse_codex_event,
            stdin_data=input.encode("utf-8"),
            cli_label="codex",
        ):
            if sid and not self._session_id:
                self._session_id = sid
            yield ev
