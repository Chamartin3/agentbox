"""Value types for the runner-agnostic conversation view."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ContentPart:
    type: Literal["text", "thinking", "tool_use", "tool_result"]
    byte_len: int
    body: str | None = None
    tool_name: str | None = None
    tool_use_id: str | None = None


@dataclass
class Turn:
    index: int
    role: Literal["user", "assistant", "system", "tool"]
    ts: str | None = None
    stop_reason: str | None = None
    usage: dict | None = None
    content: list[ContentPart] = field(default_factory=list)


@dataclass
class TokenTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_chars: int = 0
    text_chars: int = 0
    stop_max_tokens: int = 0
    stop_end_turn: int = 0
    cost_usd: float | None = None


@dataclass
class ConversationView:
    run_id: str
    session_id: str | None
    source_format: str
    source_uri: str | None
    totals: TokenTotals
    turns: list[Turn] = field(default_factory=list)
