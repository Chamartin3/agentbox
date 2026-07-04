"""Backend adapter for the OpenCode CLI.

``render()`` builds argv/env from the ``AgentDef`` and ``run()`` streams
events from the OpenCode subprocess directly.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.engines.backends.opencode.stream import _run_opencode_stream

from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
)
from agentbox.core.engines.contracts.base import BackendAdapter, RenderedConfig
from agentbox.core.engines.backends.opencode.render import build_opencode_items
from agentbox.core.engines.backends.opencode.session import (  # noqa: F401
    parse_event_stream_with_thinking,
    strip_code_fences,
)
from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.translation import intersect_allowed_tools
from agentbox.core.data.workenv import Item, WorkenvConfig

__all__ = [
    "OpenCodeBackend",
    "parse_event_stream_with_thinking",
    "strip_code_fences",
]

_NAME = "opencode"
_DEFAULT_OPENCODE_MODEL = "opencode/deepseek-v4-flash-free"


class OpenCodeBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "opencode-session"
    default_model = _DEFAULT_OPENCODE_MODEL

    def __init__(self) -> None:
        self._session_id: str | None = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return self._session_id

    def build_workspace_items(self, config: WorkenvConfig) -> list[Item]:
        return build_opencode_items(config)

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

        # Effective tools = agent ∩ workspace (canonical).
        effective_tools: set = set()
        if runtime_config is not None:
            effective_tools = intersect_allowed_tools(
                set(runtime_config.allowed_tools),
                ws_allowed_tools,
            )

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            agent_meta={
                "timeout_seconds": timeout_seconds,
                "effective_tools": sorted(effective_tools),
            },
            model=model,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        if shutil.which("opencode") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="opencode CLI not found")
            return

        yield LogEvent(
            run_id=run_id,
            message=f"$ opencode run --stdin ... (cwd={rendered.cwd})",
        )

        stdin_data = input.encode("utf-8")

        async for ev in _run_opencode_stream(
            self,
            run_id,
            rendered.argv,
            rendered.cwd,
            dict(rendered.env),
            timeout=rendered.agent_meta.get("timeout_seconds"),
            stdin_data=stdin_data,
        ):
            yield ev
