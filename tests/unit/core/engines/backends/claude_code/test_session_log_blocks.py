"""Content-block summarization in the Claude CLI session-log parser."""

from __future__ import annotations

from agentbox.core.data.constants import ContentBlockType
from agentbox.core.engines.backends.claude_code.session_log import _summarize_content


def test_redacted_thinking_maps_to_thinking() -> None:
    parts = _summarize_content(
        [{"type": "redacted_thinking", "data": "opaque-ciphertext"}],
        include_bodies=True,
    )
    assert len(parts) == 1
    assert parts[0].type == ContentBlockType.THINKING
    assert parts[0].body == "[redacted thinking]"


def test_unknown_block_still_falls_back_to_placeholder() -> None:
    parts = _summarize_content([{"type": "some_future_type"}], include_bodies=True)
    assert len(parts) == 1
    assert parts[0].type == ContentBlockType.TEXT
    assert parts[0].body == "[unhandled block: some_future_type]"
