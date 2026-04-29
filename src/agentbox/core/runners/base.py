"""Runner abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from agentbox.api.events import RunEvent
from agentbox.core.constants import RunnerKind
from agentbox.core.definitions import AgentDef


@dataclass
class RunRequest:
    run_id: str
    agent: AgentDef
    input: str
    workdir: Path
    project_root: Path
    session_id: str | None = None


class Runner(ABC):
    """A Runner takes a RunRequest and yields RunEvents as the agent executes.

    Contract for implementations:

    - MUST always yield a terminal ``DoneEvent`` (``ok=True`` or ``ok=False``).
      If an exception escapes ``run()``, the executor catches it and marks the
      run as failed — but the preferred pattern is to catch internally and
      yield ``DoneEvent(ok=False, error=...)``.

    - Timeout is enforced by the executor (``asyncio.wait_for``); runners do
      not need to implement their own timeout logic.

    - The ``workdir`` on ``RunRequest`` is created and owned by the executor.
      Runners may write to it freely; they must NOT delete it.

    - ``RunnerSpec`` fields by runner kind:

      ``claude_code``: model, mcp_config_path, allowed_tools, extra_args, timeout_seconds
      ``opencode``:    extra_args, timeout_seconds
      ``pydantic_ai``: agent_module, output_schema_path, max_validation_retries, timeout_seconds

    Conversation sources:

    - ``conversation_format`` identifies which ``ConversationSource`` can load
      this runner's native conversation log. Set to ``None`` (default) when the
      runner has no native log — the executor falls back to the agentbox
      JSONL transcript.
    - ``conversation_uri()`` returns the storage path (opaque string) for the
      conversation log, or ``None`` if unknown until run time.
    """

    kind: RunnerKind = RunnerKind.ADAPTER

    conversation_format: ClassVar[str | None] = None

    def conversation_uri(
        self,
        run_id: str,
        transcript_path: str | None = None,
    ) -> str | None:
        """Return the URI for this run's native conversation log, if known.

        Override in subclasses that know their storage layout (e.g. Claude
        CLI's session JSONL, OpenCode's session directory). Matches the
        ``BackendAdapter`` signature so the executor can call both
        uniformly.
        """
        return None

    @abstractmethod
    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        """Execute the agent and stream events."""
        raise NotImplementedError
        yield  # pragma: no cover  - signals async generator type to linters
