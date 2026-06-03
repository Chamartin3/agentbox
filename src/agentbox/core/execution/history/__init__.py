"""Runner-agnostic conversation sources.

Each runner declares a ``conversation_format``; a registry dispatches on
that format to a ``ConversationSource`` implementation that knows how to
load and parse the runner's native conversation log into a uniform
``ConversationView``.
"""

from agentbox.core.execution.history.base import ConversationSource
from agentbox.core.execution.history.registry import available_formats, get
from agentbox.core.execution.history.types import (
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
    "Turn",
    "available_formats",
    "get",
]
