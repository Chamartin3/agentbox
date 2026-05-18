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

from agentbox.api.events import DoneEvent, RunEvent
from agentbox.core.run.streaming.session import RunStreamSession
from agentbox.core.run.validation import ValidationResult, validate_output


@dataclass(frozen=True)
class BackendRunResult:
    """Terminal status reported by a backend after a run completes.

    Backends report their *runner-level* outcome here — did the
    subprocess exit cleanly, was there a runtime error, what was the
    exit code. Validation outcome is the executor's concern: it runs
    schema checks AFTER ``run_into_session`` returns and adjusts the
    final state accordingly before emitting the terminal ``DoneEvent``.

    Why a return value instead of a streamed ``DoneEvent``: the executor
    must enforce "DoneEvent is the last event emitted" so WS clients
    see validation results before they treat the run as terminal.
    Returning the status keeps the backend out of the ordering decision.
    """

    ok: bool
    exit_code: int | None = None
    error: str | None = None
    status: str | None = None  # "ok" | "error" | "timeout" | None


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

    Set by the adapter during ``render()`` from EffectiveRunnerConfig or
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
    """Model used when the effective runner config omits a model.
    ``None`` means the backend has no default — the upstream CLI / SDK
    picks one."""

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
        populate :attr:`RenderedConfig.model` with the effective model.
        ``runner_config`` is the authoritative runtime dispatch config;
        adapters must not read ``agent.runner`` for backend/model/timeout/
        extra_args fallback.
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

        This is the lower-level iterator-based entry point. New code
        should use :meth:`run_into_session` instead — it pushes events
        through the executor's central capture object and returns the
        terminal status as a value. Subclasses can keep implementing
        ``run`` (the bridge below adapts it) or override
        ``run_into_session`` directly for cleaner control flow.
        """
        if False:
            yield  # pragma: no cover — signals async generator

    async def run_into_session(
        self,
        rendered: RenderedConfig,
        input: str,
        session: RunStreamSession,
    ) -> BackendRunResult:
        """Execute the agent, pushing events through ``session``.

        Canonical entry point — the executor calls this. Returns the
        terminal status as a :class:`BackendRunResult`; the executor
        runs validation against the accumulated output and then emits
        the final ``DoneEvent`` itself, guaranteeing it lands LAST.

        Default implementation bridges the legacy
        ``run() -> AsyncIterator`` contract by pumping each event into
        the session, intercepting ``DoneEvent`` to extract terminal
        status (without emitting it — the executor will). Backends that
        want to skip the iterator overhead, integrate native validation,
        or simplify their control flow can override this directly.

        The default exists so the 5 existing iterator-based backends
        keep working unchanged through the new central path. Backends
        migrated to direct ``session.emit*`` calls override this method.
        """
        result = BackendRunResult(ok=False)
        async for ev in self.run(rendered, input, session.run_id):
            if isinstance(ev, DoneEvent):
                # Capture terminal status; do NOT publish — the executor
                # will emit the final DoneEvent after validation runs.
                result = BackendRunResult(
                    ok=ev.ok,
                    exit_code=ev.exit_code,
                    error=ev.error,
                    status=ev.status,
                )
                continue
            session.emit(ev)
        return result

    def validate_output(
        self,
        agent: Any,
        workdir: Path,
        output: str | None,
        *,
        project_root: Path | None = None,
    ) -> ValidationResult:
        """Validate ``output`` against the agent's declared schema.

        Default implementation resolves the schema from
        ``agent._composed_schema`` (preferred — set by the composition
        pipeline or by the output_schema prompt-binding) or from
        ``runner.output_schema_path`` (legacy disk path), and runs the
        engine declared by ``runner.output_validation_engine``.

        Backends that already produce typed objects (token / pydantic-ai
        with structured returns) should override and either short-circuit
        with ``ValidationResult(ok=True, engine="pydantic")`` or wrap
        their native validation error.

        Lives on the adapter (not the executor) so validation can run
        in the same place as the rest of the backend's run lifecycle —
        keeps the executor backend-agnostic and lets the
        ``BackendAdapter`` ABC own the full "render → run → validate"
        contract.
        """
        return validate_output(agent, workdir, output, project_root=project_root)

    # ----- protected helpers (shared across backends) ----------------------

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
