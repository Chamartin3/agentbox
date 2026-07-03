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
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import yaml

from agentbox.core.events import RunEvent
from agentbox.core.tools.canonical import CanonicalTool
from ._mcp_types import McpToolSpec
from .rendered import RenderedConfig
from .views import ComposedView, RuntimeConfigView

if TYPE_CHECKING:
    from agentbox.core.workspaces.generation.config import WorkenvConfig
    from agentbox.core.workspaces.generation.payload import Item


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

    def recipe_path(self) -> Path | None:
        """Return the path to this backend's generation recipe, if any.

        Defaults to ``recipe.yaml`` in the backend's package directory.
        Backends without a recipe (e.g. in-process runners) can leave the
        default, which returns ``None`` when the file does not exist.
        """
        candidate = Path(inspect.getfile(self.__class__)).parent / "recipe.yaml"
        return candidate if candidate.exists() else None

    def build_workspace_items(self, config: "WorkenvConfig") -> "list[Item]":
        """Engine-specific workspace config files, as generator ``Item``s.

        The generic generator builds everything a ``recipe.yaml`` can
        describe (layout + templates + serialization). Logic that data
        can't express — agent tables, permission merges, engine-shaped
        config blobs like ``opencode.json`` — is produced here, in the
        backend that owns that engine's format. Default: none.
        """
        return []

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
        ws_allowed_tools: set[CanonicalTool] | None = None,
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

        ``runtime_config``, ``host_capabilities``, and ``ws_allowed_tools``
        are pre-computed by the executor so backends never import
        ``core.agents.*`` or ``core.workspace.*`` directly.
        """

    @abstractmethod
    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        """Execute the agent using ``rendered`` and stream events.

        Workspace files are materialised on disk by the workspace generator
        before this method is called. The implementation must yield a
        terminal ``DoneEvent``.
        """
        if False:
            yield  # pragma: no cover — signals async generator

    # ----- protected helpers (shared across backends) ----------------------

    def context_filename(self) -> str:
        """Instruction-file name this backend reads, per its ``recipe.yaml``.

        Claude reads ``CLAUDE.md``; OpenCode / Codex / Pi read ``AGENTS.md``.
        Sourced from the backend's own recipe (``layout.context``) so the
        adapter materialises only the file its engine actually reads. Reads
        the recipe file directly to avoid an engines→workspaces import.
        Defaults to ``CLAUDE.md`` when the backend has no recipe.
        """
        path = self.recipe_path()
        if path is not None and path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            ctx = (data.get("layout") or {}).get("context")
            if isinstance(ctx, str) and ctx:
                return ctx
        return "CLAUDE.md"

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
