"""Backend adapter for the OpenCode CLI.

``render()`` builds argv/env from the ``AgentDef`` and ``run()`` streams
events from the OpenCode subprocess directly.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar, TypedDict

from agentbox.core.data.jsontypes import RawJson

from agentbox.core.engines.backends.opencode.stream import _run_opencode_stream

from agentbox.core.data.events import (
    DoneEvent,
    LogEvent,
    RunEvent,
)
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.engines.backends.credenv import build_run_env
from agentbox.core.data import RenderedConfig
from agentbox.core.engines.backends.opencode.render import build_opencode_items
from agentbox.core.engines.backends.opencode.tools import (
    NATIVE_BUILTINS as _OPENCODE_BUILTINS,
    NATIVE_TOOLS as _OPENCODE_TOOLS,
)
from agentbox.core.engines.backends.opencode.session import (  # noqa: F401
    parse_event_stream_with_thinking,
    strip_code_fences,
)
from agentbox.core.data import CanonicalTool
from agentbox.core.data.workenv import Item, WorkspaceConfig

__all__ = [
    "OpenCodeBackend",
    "parse_event_stream_with_thinking",
    "strip_code_fences",
]

_NAME = "opencode"

# Terminal fallback model when neither the runner config nor a runner profile
# supplies one. The system-default runner profile is the real source of truth;
# this only guards the case where no profile resolves at all.
_DEFAULT_MODEL = "opencode/deepseek-v4-flash-free"


class _OpenCodeProviderOptions(TypedDict):
    """opencode provider options (e.g., baseURL for ollama)."""
    baseURL: str


class _OpenCodeProviderEntry(TypedDict):
    """opencode provider configuration entry (ollama-ai-provider-v2)."""
    npm: str
    options: _OpenCodeProviderOptions
    models: dict[str, RawJson]


class OpenCodeProviderBlock(TypedDict):
    """opencode provider block derived from runner profile.

    Maps provider names (e.g., 'ollama') to their configuration entries.
    """
    ollama: _OpenCodeProviderEntry


def _normalize_model_id(model: str, provider: str | None) -> str:
    """agentbox stores ``ollama:qwen3:8b``; opencode addresses ``ollama/qwen3:8b``.

    Only rewrite when a provider is set and the id is ``provider:...`` shaped.
    An already ``provider/model`` id (contains ``/``) is left untouched.
    """
    if provider and ":" in model and "/" not in model:
        return f"{provider}/{model.split(':', 1)[1]}"
    return model


def _build_provider_block(runner_config: Any, model: str) -> OpenCodeProviderBlock | None:
    """opencode provider entry derived from the runner profile.

    ponytail: ollama only — the one keyless local provider the QA suite runs.
    Add openrouter/openai here (they need api_key_env wiring) when a profile
    actually asks for them.
    """
    provider = getattr(runner_config, "provider", None)
    base_url = getattr(runner_config, "base_url", None)
    if provider != "ollama" or not base_url:
        return None
    # ollama-ai-provider-v2 talks to the native /api endpoint; profiles store
    # the OpenAI-compatible /v1 base_url, so swap the suffix.
    api_url = base_url[: -len("/v1")] + "/api" if base_url.endswith("/v1") else base_url
    model_id = model.split("/", 1)[1] if "/" in model else model
    return OpenCodeProviderBlock(
        ollama=_OpenCodeProviderEntry(
            npm="ollama-ai-provider-v2",
            options=_OpenCodeProviderOptions(baseURL=api_url),
            models={model_id: {}},
        )
    )


def _merge_opencode_json(path: Path, provider_block: OpenCodeProviderBlock) -> None:
    """Deep-merge ``{provider: ...}`` into an existing/new opencode.json.

    The workspace generator already wrote the base config; we only add the
    provider field. agentbox's block wins on conflict. Idempotent.
    """
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data.setdefault("provider", {}).update(provider_block)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _opencode_tool_gates(
    allowed: set[CanonicalTool], forbidden: set[CanonicalTool]
) -> dict[str, bool]:
    """Map every gated opencode builtin to its enabled/disabled flag.

    opencode auto-injects all builtins under --dangerously-skip-permissions, so
    the allow-list is enforced by explicitly disabling everything it does not
    grant. An empty allow-list therefore yields "no builtins" — the behaviour a
    headless envelope agent needs. ``skill`` is not in NATIVE_BUILTINS and stays
    enabled (governed separately).
    """
    granted = {_OPENCODE_TOOLS[t] for t in (allowed - forbidden) if t in _OPENCODE_TOOLS}
    return {str(tool): tool in granted for tool in _OPENCODE_BUILTINS}


def _merge_opencode_tools(path: Path, tool_gates: dict[str, bool]) -> None:
    """Merge builtin enable/disable flags into opencode.json's ``tools`` map.

    Preserves entries the workspace generator wrote (e.g. ``skill: true``);
    our explicit gates win on conflict. Idempotent.
    """
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data.setdefault("tools", {}).update(tool_gates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


class OpenCodeBackend(BackendAdapter):
    name = _NAME
    conversation_format: ClassVar[str | None] = "opencode-session"

    def __init__(self) -> None:
        self._session_id: str | None = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        return self._session_id

    def build_workspace_items(self, config: WorkspaceConfig) -> list[Item]:
        return build_opencode_items(config)

    def declared_tools(self) -> list[CanonicalTool]:
        return list(_OPENCODE_TOOLS.keys())

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
        extra_args = list(
            getattr(runner_config, "extra_args", None)
            or getattr(agent_runner, "extra_args", None)
            or []
        )
        model = getattr(runner_config, "model", None) or _DEFAULT_MODEL

        provider = getattr(runner_config, "provider", None)
        model = _normalize_model_id(model, provider)

        # Inject a per-run provider block so opencode can reach a local
        # (non-cloud) provider like ollama. Merges into the workspace
        # opencode.json the generator already wrote at workdir root.
        provider_block = _build_provider_block(runner_config, model)
        if provider_block:
            _merge_opencode_json(workdir / "opencode.json", provider_block)

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

        env = build_run_env(creds)
        env["PWD"] = str(workdir)

        timeout_seconds = getattr(agent_runner, "timeout_seconds", None)

        # Gate opencode's auto-injected builtins by the agent allow-list.
        # Empty allow-list ⇒ no builtins (opencode would otherwise expose bash,
        # write, webfetch, … under --dangerously-skip-permissions). Written into
        # opencode.json since the CLI has no allow-list flag — only a tools map.
        allowed: set[CanonicalTool] = set(
            getattr(runtime_config, "allowed_tools", None) or ()
        )
        forbidden: set[CanonicalTool] = set(
            getattr(runtime_config, "forbidden_tools", None) or ()
        )
        tool_gates = _opencode_tool_gates(allowed, forbidden)
        _merge_opencode_tools(workdir / "opencode.json", tool_gates)
        effective_tools = sorted(name for name, on in tool_gates.items() if on)

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
