"""OpenCode backend — public facade."""

from agentbox.core.engines.backends.opencode.adapter import (
    OpenCodeBackend,
    parse_event_stream_with_thinking,
    strip_code_fences,
)

__all__ = [
    "OpenCodeBackend",
    "parse_event_stream_with_thinking",
    "strip_code_fences",
]
