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

import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from agentbox.core.data import RunEvent
from ._mcp_types import McpToolSpec
from .rendered import RenderedConfig
from .views import ComposedView, RuntimeConfigView

if TYPE_CHECKING:
    from agentbox.core.data import AgentDef


class HasAgentConfig(Protocol):
    """An object carrying a ``_config_json`` attribute (e.g. AgentDef).

    AgentDef sets this via ``__dict__`` in ``from_db_row()`` so it isn't a
    declared pydantic field; the Protocol lets callers consume it without
    importing the full Agents domain.
    """

    _config_json: dict[str, object] | str | None


class ComposedContext(Protocol):
    """Minimal interface for composed prompt metadata.

    Backends only need ``system`` and ``user`` from the composed result.
    """

    system: str
    user: str


@dataclass(frozen=True)
class McpConfig:
    """MCP server configuration shared across backends."""

    server_name: str = "mcp"
    url: str | None = None
    transport: str = "http"
    command: list[str] | None = None


class BackendConfigGenerator(ABC):
    """Translate prompts/ into a backend's native run-directory format."""

    @abstractmethod
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedContext,
        mcp: McpConfig | None = None,
    ) -> None:
        """Write backend-specific files into ``backend_dir``.

        Implementations must be idempotent — they should skip files that
        already exist unless regeneration is explicitly requested.
        """
        raise NotImplementedError


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

    def recipe_path(self) -> Path | None:
        """Return the path to this backend's generation recipe, if any.

        Defaults to ``recipe.yaml`` in the backend's package directory.
        Backends without a recipe (e.g. in-process runners) can leave the
        default, which returns ``None`` when the file does not exist.
        """
        candidate = Path(inspect.getfile(self.__class__)).parent / "recipe.yaml"
        return candidate if candidate.exists() else None

    @abstractmethod
    def render(
        self,
        agent: object,  # AgentDef — avoid circular ref at runtime; accept duck
        workdir: Path,
        mcp_tools: list[McpToolSpec] | None = None,
        creds: dict[str, str] | None = None,
        runner_config: Any | None = None,
        composed: ComposedView | None = None,
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
        """
        if False:
            yield  # pragma: no cover — signals async generator

    # ----- protected helpers (shared across backends) ----------------------

    def _collect_system_files(
        self,
        agent: Any,
        workdir: Path,
        composed: ComposedView | None = None,
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
        composed: ComposedView | None = None,
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
