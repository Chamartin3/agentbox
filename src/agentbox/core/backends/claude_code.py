"""Backend adapter for the Claude Code CLI runner.

Wraps ``agentbox.core.runners.claude_code`` — ``render()`` builds
argv/env from the ``AgentDef`` and workspace, ``run()`` delegates to the
existing subprocess loop.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentbox.api.events import DoneEvent, LogEvent, RunEvent
from agentbox.core.backends.base import BackendAdapter, RenderedConfig
from agentbox.core.constants import DEFAULT_RUNNER_TIMEOUT_SECONDS
from agentbox.core.runners.claude_code import _run_claude
from agentbox.core.workspaces import load_capabilities

_NAME = "claude_code"


class ClaudeCodeBackend(BackendAdapter):
    name = _NAME
    conversation_format: str | None = "claude-cli-jsonl"

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        # The Claude CLI source uses transcript_path to locate the
        # native session JSONL under $CLAUDE_CONFIG_DIR/projects/.
        return transcript_path

    def render(
        self,
        agent: Any,
        workdir: Path,
        mcp_tools: list[dict] | None = None,
        creds: dict | None = None,
    ) -> RenderedConfig:
        spec = agent.runner
        model = self._resolve_model(spec)
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
            spec.allowed_tools, capabilities.get("allowed_tools")
        )
        if effective_tools:
            argv += ["--allowedTools", *effective_tools]

        argv += ["--output-format", "json", "--permission-mode", "bypassPermissions"]
        argv += spec.extra_args

        env = dict(os.environ)
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)

        return RenderedConfig(
            argv=argv,
            env=env,
            cwd=Path("."),
            files=self._collect_system_files(agent, workdir),
            agent_meta={"timeout_seconds": spec.timeout_seconds},
            model=model,
        )

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        import shutil

        if shutil.which("claude") is None:
            yield DoneEvent(run_id=run_id, ok=False, error="claude CLI not found")
            return

        yield LogEvent(
            run_id=run_id,
            message=f"$ claude -p ... (cwd={rendered.cwd})",
        )

        async for ev in _run_claude(
            run_id,
            rendered.argv,
            rendered.cwd,
            dict(rendered.env),
            rendered.agent_meta.get("timeout_seconds", DEFAULT_RUNNER_TIMEOUT_SECONDS),
            stdin_data=input.encode("utf-8"),
        ):
            yield ev


def _intersect_allowed_tools(
    agent_tools: list[str], workspace_tools: list[str] | None
) -> list[str]:
    if not agent_tools and not workspace_tools:
        return []
    if not agent_tools:
        return list(workspace_tools or [])
    if not workspace_tools:
        return list(agent_tools)
    ws_set = set(workspace_tools)
    return [t for t in agent_tools if t in ws_set]
