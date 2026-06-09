"""BackendAdapter abstract base class.

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

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

if TYPE_CHECKING:
    from agentbox.core.execution.prepare.prompts import ComposedState
    from agentbox.core.execution.streaming.session import RunStreamSession

from agentbox.core.data import DoneEvent, RunEvent
from agentbox.core.engines.render.postrender import (
    inject_agent_tools_mcp,
    inject_host_env_mcp,
)
from agentbox.core.execution.output_validate import ValidationResult, validate_output

from ._mcp_types import McpToolSpec
from .rendered import RenderedConfig
from .requests import BackendRunResult, PostRenderContext, RunRequest
from .views import PythonAgentConfigView, RuntimeConfigView


class HasAgentConfig(Protocol):
    """An object carrying a ``_config_json`` attribute (e.g. AgentDef).

    AgentDef sets this via ``__dict__`` in ``from_db_row()`` so it isn't a
    declared pydantic field; the Protocol lets callers consume it without
    importing the full Agents domain.
    """

    _config_json: dict[str, object] | str | None


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
        composed: "ComposedState | None" = None,
        *,
        runtime_config: RuntimeConfigView | None = None,
        host_capabilities: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> RenderedConfig:
        """Analyse ``agent`` and ``workdir``, return a frozen run config.

        Must be stateless: calling it twice on the same inputs must
        produce the same ``RenderedConfig`` (same digest). Must NOT
        write to disk; the executor handles materialisation. Must
        populate :attr:`RenderedConfig.model` with the effective model.
        ``runner_config`` is the authoritative runtime dispatch config;
        adapters must not read ``agent.runner`` for backend/model/timeout/
        extra_args fallback.

        ``runtime_config`` and ``host_capabilities`` are pre-computed by
        the executor so backends never import ``core.agents.*`` or
        ``core.workspace.*`` directly.
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
        session: "RunStreamSession",
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

    def post_render(
        self,
        rendered: RenderedConfig,
        ctx: PostRenderContext,
    ) -> None:
        """Post-materialization hook — called by the executor after
        ``render()``'s files have been written into ``ctx.run_dir``.

        Default implementation injects the agentbox MCP servers
        (host-env, agent-tools) into the generated ``claude_mcp.json``
        when the executor passes resolved grants. Backends that don't
        consume ``claude_mcp.json`` (in-process backends like ``token``,
        or backends with a different MCP config format) override to
        no-op or to write their own format.

        Must be idempotent: the executor may call it multiple times
        across re-renders. Must not raise — the executor wraps the call
        in a try/except and logs.
        """
        if ctx.host_env_grants:
            inject_host_env_mcp(
                run_dir=ctx.run_dir,
                grants=ctx.host_env_grants,
                workspace_id=ctx.workspace_id or "",
                workdir=ctx.workdir,
                db_path=ctx.db_path,
            )
        if ctx.agent_tool_grants:
            inject_agent_tools_mcp(
                run_dir=ctx.run_dir,
                grants=ctx.agent_tool_grants,
                agent_id=ctx.agent_id,
                workdir=ctx.workdir,
                db_path=ctx.db_path,
            )

    def validate_output(
        self,
        agent: Any,
        workdir: Path,
        output: str | None,
        *,
        project_root: Path | None = None,
        store: Any | None = None,
        composed: "ComposedState | None" = None,
    ) -> ValidationResult:
        """Validate ``output`` against the agent's declared schema.

        Default implementation resolves the schema from ``composed.schema``
        (preferred — set by the composition pipeline or the
        ``output_schema`` prompt-binding) or from
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
        return validate_output(
            agent,
            workdir,
            output,
            project_root=project_root,
            store=store,
            composed=composed,
        )

    # ----- protected helpers (shared across backends) ----------------------

    def _collect_system_files(
        self,
        agent: Any,
        workdir: Path,
        composed: "ComposedState | None" = None,
    ) -> dict[Path, bytes]:
        """Collect the CLAUDE.md system-context file for materialisation.

        Prefers ``composed.system`` (set by the prompt composer when
        fragments are merged) over the on-disk ``CLAUDE.md`` in the
        workdir. Returns an empty dict when neither exists.
        """
        files: dict[Path, bytes] = {}
        composed_system = composed.system if composed is not None else None
        if composed_system is not None:
            files[Path("CLAUDE.md")] = composed_system.encode("utf-8")
        else:
            claude_md = workdir / "CLAUDE.md"
            if claude_md.exists():
                files[Path("CLAUDE.md")] = claude_md.read_bytes()
        return files

    def _resolve_prompt(
        self,
        agent: Any,
        workdir: Path,
        composed: "ComposedState | None" = None,
    ) -> str:
        """Resolve the system prompt for in-process backends.

        Prefers ``composed.system`` (set by the prompt composer) and
        falls back to ``agent.load_prompt(workdir.parent)`` when
        available. Returns ``""`` when neither resolves.
        """
        composed_system = composed.system if composed is not None else None
        if composed_system is not None:
            return composed_system
        prompt_text = getattr(agent, "load_prompt", None)
        if prompt_text is None:
            return ""
        return prompt_text(workdir.parent) or ""
