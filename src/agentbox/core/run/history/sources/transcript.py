"""Conversation source that parses the agentbox JSONL transcript.

Acts as the universal fallback when no runner-native source exists
(e.g. subprocess or raw backends). For best results, runners that
have no native log should write full ``text``/``thinking`` content
into their events.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.data import read_transcript
from agentbox.core.run.history.base import ConversationSource
from agentbox.core.run.history.types import (
    ContentPart,
    ConversationView,
    TokenTotals,
    Turn,
)

if TYPE_CHECKING:
    from agentbox.core.data import RunRecord


def _events_to_conversation_view(
    *,
    events: list[dict],
    run_id: str,
    source_format: str,
    source_uri: str | None,
    include_bodies: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> ConversationView:
    """Shared helper: convert agentbox transcript events into a ConversationView.

    Handles the common event types: text, thinking, log, usage, done, timeout,
    tool_call, tool_result.
    """
    totals = TokenTotals()
    turns: list[Turn] = []
    session_id: str | None = None
    turn_idx = 0

    for ev in events:
        ev_type = ev.get("type", "")
        ts = ev.get("ts")

        if ev_type == "text":
            text = ev.get("text", "")
            role = ev.get("role") or "assistant"
            parts = [
                ContentPart(
                    type="text",
                    byte_len=len(text),
                    body=text if include_bodies else None,
                )
            ]
            totals.text_chars += len(text)
            turns.append(
                Turn(
                    index=turn_idx,
                    role=role,
                    ts=ts,
                    content=parts,
                )
            )
            turn_idx += 1

        elif ev_type == "thinking":
            body = ev.get("text", "") or ev.get("thinking", "") or ""
            parts = [
                ContentPart(
                    type="thinking",
                    byte_len=len(body),
                    body=body if include_bodies else None,
                )
            ]
            totals.thinking_chars += len(body)
            turns.append(
                Turn(
                    index=turn_idx,
                    role="assistant",
                    ts=ts,
                    content=parts,
                )
            )
            turn_idx += 1

        elif ev_type == "tool_call":
            tool_name = ev.get("tool_name") or ev.get("tool") or ev.get("name", "")
            inp = ev.get("input") or ev.get("arguments", {})
            import json as _json

            body_str = _json.dumps(inp) if inp else ""
            parts = [
                ContentPart(
                    type="tool_use",
                    byte_len=len(body_str),
                    body=body_str if include_bodies else None,
                    tool_name=tool_name,
                )
            ]
            turns.append(
                Turn(
                    index=turn_idx,
                    role="assistant",
                    ts=ts,
                    content=parts,
                )
            )
            turn_idx += 1

        elif ev_type == "tool_result":
            output = (
                ev.get("output", "")
                or ev.get("text", "")
                or ev.get("result_excerpt", "")
                or ""
            )
            parts = [
                ContentPart(
                    type="tool_result",
                    byte_len=len(output),
                    body=output if include_bodies else None,
                )
            ]
            turns.append(
                Turn(
                    index=turn_idx,
                    role="tool",
                    ts=ts,
                    content=parts,
                )
            )
            turn_idx += 1

        elif ev_type == "usage":
            totals.input_tokens += int(ev.get("input_tokens") or 0)
            totals.output_tokens += int(ev.get("output_tokens") or 0)
            totals.cache_read_tokens += int(ev.get("cache_read_tokens") or 0)
            totals.cache_write_tokens += int(ev.get("cache_write_tokens") or 0)
            cost = ev.get("cost_usd")
            with suppress(TypeError, ValueError):
                totals.cost_usd = float(cost) if cost is not None else totals.cost_usd

        elif ev_type == "log":
            # Stderr log lines. Only ``warn``/``error`` are surfaced as
            # turns (with role ``system``) because info/debug logs are
            # noisy and not part of the conversation. The full set is
            # still available via ``get_run_logs``.
            level = ev.get("level", "info")
            if level not in ("warn", "error"):
                continue
            message = ev.get("message", "")
            parts = [
                ContentPart(
                    type="text",
                    byte_len=len(message),
                    body=message if include_bodies else None,
                )
            ]
            turns.append(
                Turn(
                    index=turn_idx,
                    role="system",
                    ts=ts,
                    content=parts,
                )
            )
            turn_idx += 1

        elif ev_type == "timeout":
            err = ev.get("error", "timeout")
            parts = [
                ContentPart(
                    type="text",
                    byte_len=len(err),
                    body=err if include_bodies else None,
                )
            ]
            turns.append(
                Turn(
                    index=turn_idx,
                    role="system",
                    ts=ts,
                    content=parts,
                )
            )
            turn_idx += 1

        elif ev_type == "done":
            if session_id is None:
                session_id = ev.get("session_id") or ev.get("run_id")

    page = turns[offset : offset + limit]
    return ConversationView(
        run_id=run_id,
        session_id=session_id,
        source_format=source_format,
        source_uri=source_uri,
        totals=totals,
        turns=page,
    )


class TranscriptSource(ConversationSource):
    """Parse the agentbox JSONL transcript into a ``ConversationView``.

    The transcript contains all events emitted during a run (TextEvent,
    ThinkingEvent, UsageEvent, DoneEvent, etc.). This source reconstructs
    a conversation-like view from those events.

    For runners with richer native logs (Claude CLI JSONL, OpenCode session
    export), prefer the runner-specific source. This is the fallback for
    subprocess and raw backends.
    """

    format = "agentbox-transcript"

    def __init__(self, transcript_path: Path | None = None) -> None:
        self._transcript_path = transcript_path

    @classmethod
    def for_run(cls, run: RunRecord) -> ConversationSource | None:
        if not run.transcript_path:
            return None
        return cls(transcript_path=Path(run.transcript_path))

    def load(
        self,
        *,
        include_bodies: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationView:
        tp = self._transcript_path
        if tp is None or not tp.exists():
            return ConversationView(
                run_id="?",
                session_id=None,
                source_format=self.format,
                source_uri=str(tp) if tp else None,
                totals=TokenTotals(),
            )

        events = read_transcript(tp)
        return _events_to_conversation_view(
            events=events,
            run_id="?",
            source_format=self.format,
            source_uri=str(tp),
            include_bodies=include_bodies,
            offset=offset,
            limit=limit,
        )
