"""Detect provider rate-limit / quota / auth failures in runner output.

Shared by the opencode and claude_code runners so a 429 from the LLM
provider terminates the subprocess immediately rather than waiting for
the per-run ``timeout_seconds`` to elapse.

Two detectors:

- :func:`detect_in_opencode_event` — inspects a parsed opencode JSON event
  (from ``opencode run --format json``). Opencode wraps the upstream
  error in an ``AI_APICallError`` payload with ``statusCode`` and the
  provider's response body.
- :func:`detect_in_text_line` — substring match against a stderr/log line,
  used for claude_code (its ``--output-format json`` emits a single
  envelope only at exit, so we watch stderr in real time).
"""

from __future__ import annotations

import re
from typing import Any

_FATAL_HTTP_STATUSES: frozenset[int] = frozenset({401, 402, 403, 429})

# Error ``name`` / ``type`` strings that opencode emits for unrecoverable
# upstream failures. We treat any of these — or any HTTP statusCode in
# ``_FATAL_HTTP_STATUSES`` — as a hard stop.
_FATAL_ERROR_NAMES: frozenset[str] = frozenset(
    {
        "AI_APICallError",
        "APIError",
        "FreeUsageLimitError",
        "CreditsError",
        "AuthError",
        "UnauthorizedError",
    }
)

_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b429\b"),
    re.compile(r"rate[\s_-]?limit", re.IGNORECASE),
    re.compile(r"quota", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"insufficient_quota", re.IGNORECASE),
    re.compile(r"FreeUsageLimitError", re.IGNORECASE),
    re.compile(r"invalid[_\s-]?api[_\s-]?key", re.IGNORECASE),
    re.compile(r"authentication[_\s-]?error", re.IGNORECASE),
)


def detect_in_opencode_event(evt: dict[str, Any]) -> str | None:
    """Return a short error message if ``evt`` carries a fatal API error.

    Opencode emits error events in several shapes across versions, e.g.::

        {"type": "error", "error": {"name": "AI_APICallError",
          "statusCode": 429, ...}}
        {"type": "error", "error": {"name": "APIError",
          "data": {"statusCode": 401, "message": "...",
                   "responseBody": "..."}}}

    Anything with ``type == "error"`` at the top level is treated as
    fatal (opencode emits these when it gives up retrying). We also walk
    nested dicts looking for a fatal ``statusCode`` or a known error
    ``name`` so we catch errors that don't carry the outer ``type``.
    """
    # Top-level error envelope: always treat as fatal, even if the inner
    # shape doesn't match a recognised name. Opencode only emits
    # ``type=error`` when its internal retry budget is exhausted.
    if isinstance(evt, dict) and evt.get("type") == "error":
        inner = evt.get("error")
        if isinstance(inner, dict):
            found = _walk_for_api_error(inner)
            if found is not None:
                _status, name, message = found
                prefix = f"opencode {name or 'api error'}"
                if _status:
                    prefix += f" ({_status})"
                return f"{prefix}: {message}" if message else prefix
        # Couldn't extract structured detail — still surface as fatal.
        return "opencode emitted error event"

    found = _walk_for_api_error(evt)
    if found is None:
        return None
    status, name, message = found
    if status in _FATAL_HTTP_STATUSES or (name and name in _FATAL_ERROR_NAMES):
        prefix = f"opencode {name or 'api error'}"
        if status:
            prefix += f" ({status})"
        return f"{prefix}: {message}" if message else prefix
    return None


def detect_in_text_line(line: str) -> str | None:
    """Return a short error message if ``line`` matches a rate/auth pattern."""
    s = line.strip()
    if not s:
        return None
    for pat in _TEXT_PATTERNS:
        if pat.search(s):
            return s[:300]
    return None


def _walk_for_api_error(
    node: Any, depth: int = 0
) -> tuple[int | None, str | None, str | None] | None:
    """Recursively search for an ``AI_APICallError``-ish payload.

    Returns ``(statusCode, name, message)`` or ``None``. Caps recursion
    so a pathological event can't loop us.
    """
    if depth > 6:
        return None
    if isinstance(node, dict):
        name = node.get("name") or node.get("type")
        status = node.get("statusCode") or node.get("status")
        # Newer opencode shapes tuck the http status / message inside a
        # nested ``data`` dict alongside the outer ``name``. Merge them
        # so we don't miss a fatal status because the name lives one
        # level up.
        data = node.get("data")
        if isinstance(data, dict):
            if status is None:
                status = data.get("statusCode") or data.get("status")
            inner_msg = data.get("message")
            inner_rb = data.get("responseBody")
        else:
            inner_msg = None
            inner_rb = None

        is_fatal_status = isinstance(status, int) and status in _FATAL_HTTP_STATUSES
        is_fatal_name = isinstance(name, str) and name in _FATAL_ERROR_NAMES
        if is_fatal_status or is_fatal_name:
            message = node.get("message") or inner_msg
            if not isinstance(message, str):
                rb = node.get("responseBody") or inner_rb
                if isinstance(rb, str):
                    message = rb[:200]
            return (
                int(status) if isinstance(status, int) else None,
                name if isinstance(name, str) else None,
                message if isinstance(message, str) else None,
            )
        for v in node.values():
            found = _walk_for_api_error(v, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _walk_for_api_error(v, depth + 1)
            if found is not None:
                return found
    return None
