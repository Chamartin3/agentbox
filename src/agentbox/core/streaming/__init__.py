"""Shared streaming/parsing infrastructure used by backends.

Extracted from ``agentbox.core.runners._*`` in Plan 16 Phase 3 so the
helpers can outlive the legacy ``runners/`` directory. Backend modules
should import from this package; nothing here is backend-specific.
"""

from __future__ import annotations

from agentbox.core.streaming.jsonl import stream_jsonl_subprocess
from agentbox.core.streaming.rate_limit import (
    detect_in_opencode_event,
    detect_in_text_line,
)
from agentbox.core.streaming.session import (
    CaptureSession,
    DoneAlreadyEmittedError,
    RunStreamSession,
)

__all__ = [
    "CaptureSession",
    "DoneAlreadyEmittedError",
    "RunStreamSession",
    "detect_in_opencode_event",
    "detect_in_text_line",
    "stream_jsonl_subprocess",
]
