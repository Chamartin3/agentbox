"""Typed WebSocket / transcript event envelopes.

Every event is a Pydantic model with a discriminator field `type`. The
union `RunEvent` is the wire format for the WS stream and the on-disk
transcript (one JSON object per line).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class _EventBase(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str


class ToolCallEvent(_EventBase):
    type: Literal["tool_call"] = "tool_call"
    tool: str
    arguments: dict
    call_id: str | None = None


class ToolResultEvent(_EventBase):
    type: Literal["tool_result"] = "tool_result"
    tool: str
    call_id: str | None = None
    ok: bool = True
    result_excerpt: str | None = None
    """First N chars of the result. Full payload lives in run artifacts."""


class TextEvent(_EventBase):
    type: Literal["text"] = "text"
    text: str
    role: Literal["assistant", "user", "system"] = "assistant"


class UsageEvent(_EventBase):
    type: Literal["usage"] = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    model: str | None = None


class GuardrailEvent(_EventBase):
    type: Literal["guardrail"] = "guardrail"
    name: str
    ok: bool
    message: str | None = None
    attempt: int = 0


class LogEvent(_EventBase):
    type: Literal["log"] = "log"
    level: Literal["debug", "info", "warn", "error"] = "info"
    message: str


class DoneEvent(_EventBase):
    type: Literal["done"] = "done"
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
    | GuardrailEvent
    | LogEvent
    | DoneEvent,
    Field(discriminator="type"),
]
