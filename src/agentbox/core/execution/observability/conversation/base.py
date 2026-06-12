"""Abstract base class for conversation sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from agentbox.core.data import RunRecord
from agentbox.core.execution.observability.conversation.types import ConversationView


class ConversationSource(ABC):
    """Load and parse a runner-specific conversation log into a uniform view.

    Subclasses declare their ``format`` as a ``ClassVar`` string. A registry
    (see ``registry.py``) dispatches on ``format`` at runtime.
    """

    format: ClassVar[str]

    @classmethod
    def for_run(cls, run: RunRecord) -> ConversationSource | None:
        """Construct a source for this run, or return None if not applicable.

        Subclasses MUST override when they need run-specific context (a
        transcript path, a conversation_uri, a session id). The default
        returns ``None`` rather than a context-less instance, so callers
        get a clear "no_conversation" error instead of an empty view.
        """
        return None

    @abstractmethod
    def load(
        self,
        *,
        include_bodies: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationView:
        """Load and parse the conversation.

        Args:
            include_bodies: Whether to populate ``ContentPart.body``.
            offset: Turn index to start from.
            limit: Maximum number of turns to return.

        Returns:
            A ``ConversationView`` with the requested slice of turns.
        """
        ...
