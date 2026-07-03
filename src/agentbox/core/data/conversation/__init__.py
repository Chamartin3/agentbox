"""Conversation contract and value shapes.

The ``ConversationSource`` plugin ABC (entry-point group
``agentbox.conversations``), its uniform view types, and the built-in
transcript-backed source. Lives in the ``core.data`` leaf so backend
implementations (``core.engines``) and post-run decoding
(``core.execution.observability``) can both import it without a cycle.
Runtime registry/dispatch stays in
``core.execution.observability.conversation``.
"""

from __future__ import annotations

from agentbox.core.data.conversation.base import ConversationSource
from agentbox.core.data.conversation.transcript import TranscriptSource
from agentbox.core.data.conversation.types import (
    ContentPart,
    ConversationView,
    TokenTotals,
    Turn,
)

__all__ = [
    "ContentPart",
    "ConversationSource",
    "ConversationView",
    "TokenTotals",
    "TranscriptSource",
    "Turn",
]
