"""OpenCode backend — public facade."""

from agentbox.core.engines.backends.opencode.adapter import (
    OpenCodeBackend,
    parse_event_stream_with_thinking,
    strip_code_fences,
)
from agentbox.core.engines.backends.opencode.tools import NATIVE_TOOLS

__all__ = [
    "NATIVE_TOOLS",
    "OpenCodeBackend",
    "parse_event_stream_with_thinking",
    "strip_code_fences",
]
