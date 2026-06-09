"""Backend adapter for the OpenCode CLI.

Self-contained after Plan 16 Phase 4 — ``render()`` builds argv/env
from the ``AgentDef`` and ``run()`` streams events from the OpenCode
subprocess directly.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.data import (
    DoneEvent,
    LogEvent,
    RunEvent,
)
from agentbox.core.engines.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.engines.backends.opencode.session import (
    parse_event_stream_with_thinking,
    strip_code_fences,
)

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

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: Any = None,
        creds: dict | None = None,
        runner_config: Any | None = None,
        composed: Any | None = None,
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

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            files=self._collect_system_files(agent, workdir, composed),
            agent_meta={"timeout_seconds": timeout_seconds},
            model=model,
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

        from agentbox.core.engines.backends.opencode.stream import (
            _run_opencode_stream,
        )

        async for ev in _run_opencode_stream(
            self,
            run_id,
            rendered.argv,
            rendered.cwd,
            dict(rendered.env),
            timeout=rendered.agent_meta["timeout_seconds"],
            stdin_data=stdin_data,
        ):
            yield ev
