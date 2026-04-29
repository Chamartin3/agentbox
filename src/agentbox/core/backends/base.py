"""BackendAdapter Protocol + RenderedConfig dataclass."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypedDict, runtime_checkable

from agentbox.api.events import RunEvent


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


@runtime_checkable
class BackendAdapter(Protocol):
    """Backend-agnostic adapter: renders config then runs an agent.

    A single instance is created per-run. Implementations must be cheap
    to construct (no heavy init); the expensive work happens in
    ``render()`` and ``run()``.
    """

    name: str
    """Stable identifier matching the entry-point name (e.g. ``claude_code``)."""

    conversation_format: str | None
    """Format string for the ``ConversationSource`` that can load this
    backend's native conversation log. ``None`` means no native source —
    the executor falls back to the agentbox JSONL transcript."""

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

    def render(
        self,
        agent: object,  # AgentDef — avoid circular ref at runtime; accept duck
        workdir: Path,
        mcp_tools: list[McpToolSpec] | None = None,
        creds: dict[str, str] | None = None,
    ) -> RenderedConfig:
        """Analyse ``agent`` and ``workdir``, return a frozen run config.

        This method must be stateless — calling it twice on the same
        inputs must produce the same ``RenderedConfig`` (same digest).
        It must NOT write to disk; the executor handles materialisation.
        """
        ...

    async def run(
        self,
        rendered: RenderedConfig,
        input: str,
        run_id: str,
    ) -> AsyncIterator[RunEvent]:
        """Execute the agent using ``rendered`` and stream events.

        ``rendered.files`` have already been materialised on disk by the
        executor. The implementation must yield a terminal ``DoneEvent``.
        """
        ...
        if False:
            yield  # pragma: no cover — signals async generator
