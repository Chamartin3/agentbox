"""Abstract base class for dispatch channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from agentbox.core.protocols import RunStore
from agentbox.core.execution.dispatch.channels.types import DeliveryResult
from agentbox.core.execution.dispatch.payload import CompletionPayload
from agentbox.core.execution.dispatch.policy import DispatchPolicy


class DispatchChannel(ABC):
    """One transport for completion notifications.

    Channels are registered by stable ``name`` (matching the entry-point
    key) and looked up per-run from the agent / workspace / run-level
    config. Concrete channels implement :meth:`deliver`.
    """

    name: ClassVar[str]

    @abstractmethod
    async def deliver(
        self,
        payload: CompletionPayload,
        config: dict[str, Any],
        policy: DispatchPolicy,
        *,
        run_id: str,
        broadcaster: Any | None = None,
        transcript_path: Path | None = None,
        store: RunStore | None = None,
    ) -> DeliveryResult:
        """Deliver ``payload`` according to ``config`` and ``policy``."""
        ...


__all__ = ["DeliveryResult", "DispatchChannel"]
