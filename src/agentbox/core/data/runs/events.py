"""RunEvent discriminated union — single source of truth for the wire protocol.

Every event is a Pydantic model with a discriminator field ``type``. The
union ``RunEvent`` is the wire format for the WS stream and the on-disk
transcript (one JSON object per line).

**This is the canonical home.** ``core/data/events.py`` and ``api/events.py``
are thin re-exports for backward compatibility. New code MUST import from
here (or from the ``core.execution`` facade once it lands).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from agentbox.core.constants import EventType


class _EventBase(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str


class ToolCallEvent(_EventBase):
    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    tool: str
    arguments: dict
    call_id: str | None = None


class ToolResultEvent(_EventBase):
    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT
    tool: str
    call_id: str | None = None
    ok: bool = True
    result_excerpt: str | None = None
    """First N chars of the result. Full payload lives in run artifacts."""


class TextEvent(_EventBase):
    type: Literal[EventType.TEXT] = EventType.TEXT
    text: str
    role: Literal["assistant", "user", "system"] = "assistant"
    # True when this event is an incremental chunk emitted live during
    # the run. The executor skips appending deltas to ``output_text`` —
    # a non-delta TextEvent with the consolidated/cleaned text is
    # expected after the runner finishes.
    delta: bool = False


class UsageEvent(_EventBase):
    type: Literal[EventType.USAGE] = EventType.USAGE
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    model: str | None = None


class LogEvent(_EventBase):
    type: Literal[EventType.LOG] = EventType.LOG
    level: Literal["debug", "info", "warn", "error"] = "info"
    message: str


class RetryEvent(_EventBase):
    type: Literal[EventType.RETRY] = EventType.RETRY
    attempt: int = 1
    reason: str = ""
    """Why the retry happened: 'validation_failed' | 'run_error' | 'timeout'."""
    error: str | None = None
    """The error or validation message that triggered the retry."""


class ThinkingEvent(_EventBase):
    type: Literal[EventType.THINKING] = EventType.THINKING
    text: str
    """Raw thinking / reasoning content from the model."""


class TimeoutEvent(_EventBase):
    type: Literal[EventType.TIMEOUT] = EventType.TIMEOUT
    timeout_seconds: int = 0
    """The configured timeout for this run."""
    error: str | None = None


class ValidationEvent(_EventBase):
    type: Literal[EventType.VALIDATION] = EventType.VALIDATION
    ok: bool
    attempt: int = 1
    mode: Literal["strict", "warn", "off"] = "strict"
    engine: Literal["jsonschema", "pydantic", "both", "none"] = "none"
    error: str | None = None
    """Validation error message when ok=False."""


class DoneEvent(_EventBase):
    type: Literal[EventType.DONE] = EventType.DONE
    ok: bool
    exit_code: int | None = None
    error: str | None = None
    # Specific failure category. ``"timeout"`` means the runner's
    # ``timeout_seconds`` expired before the process exited. Any other
    # non-ok run is recorded as ``"error"``. None when ``ok=True``.
    status: Literal["ok", "error", "timeout"] | None = None


RunEvent = Annotated[
    ToolCallEvent
    | ToolResultEvent
    | TextEvent
    | UsageEvent
    | LogEvent
    | RetryEvent
    | ThinkingEvent
    | TimeoutEvent
    | ValidationEvent
    | DoneEvent,
    Field(discriminator="type"),
]

__all__ = [
    "DoneEvent",
    "LogEvent",
    "RetryEvent",
    "RunEvent",
    "TextEvent",
    "ThinkingEvent",
    "TimeoutEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "UsageEvent",
    "ValidationEvent",
]
