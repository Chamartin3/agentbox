"""Session ID + output parsing helpers for the OpenCode backend."""

from __future__ import annotations

import json
import re

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def parse_event_stream_with_thinking(
    raw: str,
) -> tuple[list[str], list[str], str | None, bool]:
    """Parse opencode --format json output, extracting text and thinking parts.

    Returns (text_parts, thinking_parts, session_id, parse_failed).
    """
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    session_id: str | None = None
    any_json = False
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(evt, dict):
            continue
        any_json = True
        if session_id is None:
            sid = evt.get("sessionID")
            if isinstance(sid, str) and sid:
                session_id = sid
        if evt.get("type") == "text":
            part = evt.get("part")
            if isinstance(part, dict):
                ptype = part.get("type")
                text = part.get("text")
                if ptype == "text" and isinstance(text, str):
                    text_parts.append(text)
                elif ptype in ("thinking", "reasoning") and isinstance(text, str):
                    thinking_parts.append(text)
    return text_parts, thinking_parts, session_id, not any_json


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences from model output.

    Models often wrap JSON in ```json blocks despite being told not to.
    This strips the outer fences so downstream validation and storage
    sees clean JSON (or plain text).
    """
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    return text
