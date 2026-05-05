"""BackendAdapter abstract base + RenderedConfig dataclass.

All backend adapters inherit from :class:`BackendAdapter`. The ABC owns
the cross-backend plumbing that used to be copy-pasted into each
subclass: model resolution (with per-backend defaults), CLAUDE.md
system-file collection, and prompt resolution. Subclasses implement
only the backend-specific parts: building the command (or in-process
invocation) and streaming events.

The :attr:`RenderedConfig.model` field is the effective model that will
actually be used to run the agent. Adapters set it during ``render()``
so the executor can persist a model name even when the run never emits
a ``UsageEvent`` (e.g. on timeout).
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, TypedDict

from agentbox.api.events import RunEvent


@dataclass
class RunRequest:
    """Per-run inputs handed to a backend's ``run()`` (legacy shape, kept
    for direct in-process callers).

    Most code paths use :class:`RenderedConfig` instead — the executor
    renders once and then calls ``run(rendered, input, run_id)``. This
    dataclass survives for tests and the few helpers that still want a
    single object holding everything about a run.
    """

    run_id: str
    agent: Any  # AgentDef — avoids a circular import; runtime type is AgentDef.
    input: str
    workdir: Path
    project_root: Path
    session_id: str | None = None
    runner_profile: str | None = None
    runner_config: dict[str, Any] | None = None


class McpToolSpec(TypedDict, total=False):
    """Minimal MCP tool descriptor consumed by ``render()``."""

    name: str
    description: str
    inputSchema: dict[str, Any]


@dataclass(frozen=True)
class RenderedConfig:
    """Immutable description of an agent run's runtime configuration.

    ``render()`` on a backend adapter produces one of these. The executor
    materialises ``files`` to disk, then passes the same object to
    ``run()`` so the adapter never needs to re-inspect the workspace.
    """

    files: Mapping[Path, bytes] = field(default_factory=dict)
    """Files to materialise inside the run workdir (relative paths)."""

    argv: list[str] = field(default_factory=list)
    """Command + arguments to execute."""

    env: Mapping[str, str] = field(default_factory=dict)
    """Environment variable overrides for the subprocess."""

    cwd: Path = Path(".")
    """Working directory relative to the run workdir root."""

    agent_meta: dict[str, Any] = field(default_factory=dict)
    """Backend-specific agent metadata (e.g. agent_module, prompt for pydantic_ai
    in-process agents). Included in the digest computation."""

    model: str | None = None
    """Effective model name that will actually be used to run the agent.

    Set by the adapter during ``render()`` — combines ``spec.model`` with
    the backend's own default. Persisted by the executor so even runs
    that never emit a ``UsageEvent`` (timeouts, early crashes) keep a
    model name in the runs table.
    """

    digest: str = ""
    """sha256 over a sorted JSON serialisation of (files, argv, env, cwd, agent_meta).

    Computed automatically by ``compute_digest()``. Stable across identical
    inputs; changes when any tool, arg, or env var is added/removed.
    """

    def __post_init__(self) -> None:
        if not self.digest:
            object.__setattr__(self, "digest", self.compute_digest())

    def compute_digest(self) -> str:
        canonical = json.dumps(
            {
                "files": {str(p): h.hex() for p, h in sorted(self.files.items())},
                "argv": list(self.argv),
                "env": dict(self.env),
                "cwd": str(self.cwd),
                "agent_meta": dict(self.agent_meta),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class BackendAdapter(ABC):
    """Backend-agnostic adapter base class.

    Subclasses override the abstract :meth:`render` and :meth:`run`
    methods. Common operations (model defaulting, system-file
    collection, prompt resolution) are provided as protected helpers so
    subclasses don't reimplement them.

    A single instance is created per-run. Implementations must be cheap
    to construct (no heavy init); the expensive work happens in
    ``render()`` and ``run()``.
    """

    name: ClassVar[str]
    """Stable identifier matching the entry-point name (e.g. ``claude_code``)."""

    conversation_format: ClassVar[str | None] = None
    """Format string for the ``ConversationSource`` that can load this
    backend's native conversation log. ``None`` means no native source —
    the executor falls back to the agentbox JSONL transcript."""

    default_model: ClassVar[str | None] = None
    """Model used when ``agent.runner.model`` is empty. ``None`` means
    the backend has no default — the upstream CLI / SDK picks one."""

    # ----- public API ------------------------------------------------------

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        """Return the storage URI for this run's native conversation log.

        Override in backends that know their storage layout. The URI is
        opaque to callers — only the matching ``ConversationSource``
        implementation needs to understand it.
        """
        return None

    @abstractmethod
    def render(
        self,
        agent: object,  # AgentDef — avoid circular ref at runtime; accept duck
        workdir: Path,
        mcp_tools: list[McpToolSpec] | None = None,
        creds: dict[str, str] | None = None,
        runner_config: Any | None = None,
    ) -> RenderedConfig:
        """Analyse ``agent`` and ``workdir``, return a frozen run config.

        Must be stateless: calling it twice on the same inputs must
        produce the same ``RenderedConfig`` (same digest). Must NOT
        write to disk; the executor handles materialisation. Must
        populate :attr:`RenderedConfig.model` with the effective model
        (use :meth:`_resolve_model`). If ``runner_config`` is provided,
        honour its fields for model, timeout, extra_args, and provider routing.
        """

    @abstractmethod
    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        """Execute the agent using ``rendered`` and stream events.

        ``rendered.files`` have already been materialised on disk by
        the executor. The implementation must yield a terminal
        ``DoneEvent``.
        """
        if False:
            yield  # pragma: no cover — signals async generator

    # ----- protected helpers (shared across backends) ----------------------

    def _resolve_model(self, spec: Any) -> str | None:
        """Return ``spec.model`` if set, otherwise this backend's default.

        Backends override :attr:`default_model` rather than this method.
        Operators can also override the default at runtime via the
        ``runtime_defaults.default_model_<name>`` setting.
        """
        spec_model = getattr(spec, "model", None)
        if spec_model:
            return spec_model
        from agentbox.core.constants import runtime_default_model

        return runtime_default_model(self.name) or self.default_model

    def _collect_system_files(
        self, agent: Any, workdir: Path
    ) -> dict[Path, bytes]:
        """Collect the CLAUDE.md system-context file for materialisation.

        Prefers the in-memory ``_composed_system`` attached to the agent
        (set by the prompt composer when fragments are merged) over the
        on-disk ``CLAUDE.md`` in the workdir. Returns an empty dict when
        neither exists.
        """
        files: dict[Path, bytes] = {}
        composed_system = getattr(agent, "_composed_system", None)
        if composed_system is not None:
            files[Path("CLAUDE.md")] = composed_system.encode("utf-8")
        else:
            claude_md = workdir / "CLAUDE.md"
            if claude_md.exists():
                files[Path("CLAUDE.md")] = claude_md.read_bytes()
        return files

    def _resolve_prompt(self, agent: Any, workdir: Path) -> str:
        """Resolve the system prompt for in-process backends.

        Prefers ``agent._composed_system`` (set by the prompt composer)
        and falls back to ``agent.load_prompt(workdir.parent)`` when
        available. Returns ``""`` when neither resolves.
        """
        composed_system = getattr(agent, "_composed_system", None)
        if composed_system is not None:
            return composed_system
        prompt_text = getattr(agent, "load_prompt", None)
        if prompt_text is None:
            return ""
        return prompt_text(workdir.parent) or ""
