"""Unit tests for claude-code envelope parsing."""

from __future__ import annotations

from agentbox.core.backends.claude_code import (
    _build_usage_event,
    _parse_envelope,
)

SAMPLE = """{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "hello world",
  "total_cost_usd": 0.012345,
  "usage": {
    "input_tokens": 11,
    "output_tokens": 22,
    "cache_creation_input_tokens": 5000,
    "cache_read_input_tokens": 100
  },
  "modelUsage": {
    "claude-haiku-4-5-20251001": {"inputTokens": 11}
  }
}"""


def test_parse_envelope_basic() -> None:
    e = _parse_envelope(SAMPLE)
    assert e is not None
    assert e["result"] == "hello world"


def test_parse_envelope_with_banner() -> None:
    e = _parse_envelope("Some banner text\n" + SAMPLE)
    assert e is not None
    assert e["is_error"] is False


def test_build_usage_event() -> None:
    e = _parse_envelope(SAMPLE)
    assert e is not None
    ev = _build_usage_event("rid", e)
    assert ev is not None
    assert ev.input_tokens == 11
    assert ev.output_tokens == 22
    assert ev.cache_read_tokens == 100
    assert ev.cache_write_tokens == 5000
    assert ev.cost_usd == 0.012345
    assert ev.model == "claude-haiku-4-5-20251001"
