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

import json
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
    # opencode CLI / Vercel AI SDK error class names that surface in
    # session log lines when the upstream provider is rate-limited or
    # out of credits. opencode hides the underlying ``statusCode":429``
    # behind these class names and stops emitting to stdout after its
    # internal retries exhaust, so matching by class name is the only
    # reliable signal we get without parsing the nested JSON.
    re.compile(r"AI_APICallError", re.IGNORECASE),
    re.compile(r"AI_RetryError", re.IGNORECASE),
    re.compile(r"maxRetriesExceeded", re.IGNORECASE),
    re.compile(r"CreditsError", re.IGNORECASE),
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
        raw = str(inner)[:300] if inner is not None else "(no error payload)"
        return f"opencode emitted error event: {raw}"

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
    """Return a short error message if ``line`` matches a rate/auth pattern.

    When the line looks like a structured log (opencode session-log
    ``ERROR ... error={...}`` or a JSON blob with a nested API error),
    we extract ``name`` / ``statusCode`` / ``message`` and format a
    readable one-liner instead of returning the raw truncated text.
    """
    s = line.strip()
    if not s:
        return None
    matched = any(pat.search(s) for pat in _TEXT_PATTERNS)
    if not matched:
        return None
    pretty = _format_opencode_log_line(s)
    if pretty is not None:
        return pretty
    return s[:300]


def _format_opencode_log_line(s: str) -> str | None:
    """Extract a readable summary from an opencode session-log ERROR line.

    Opencode log lines look like::

        ERROR 2026-... service=llm providerID=opencode modelID=X
          session.id=... agent=build mode=primary
          error={"error":{"name":"AI_APICallError","url":"...",
                          "data":{"statusCode":429,"message":"..."}}}

    We pull ``providerID``, ``modelID``, and the JSON after ``error=``
    (which may be truncated mid-string when the line is long). Returns
    ``None`` when nothing structured can be extracted — caller falls
    back to the raw line.
    """
    provider = _extract_kv(s, "providerID")
    model = _extract_kv(s, "modelID")

    err_obj: dict[str, Any] | None = None
    idx = s.find("error=")
    if idx != -1:
        err_obj = _try_parse_trailing_json(s[idx + len("error="):])

    name: str | None = None
    status: int | None = None
    message: str | None = None
    if isinstance(err_obj, dict):
        found = _walk_for_api_error(err_obj)
        if found is not None:
            status, name, message = found
        else:
            # Fall back to top-level fields on the error envelope.
            inner = err_obj.get("error") if isinstance(err_obj.get("error"), dict) else err_obj
            if isinstance(inner, dict):
                name = inner.get("name") or inner.get("type")
                status = inner.get("statusCode") or inner.get("status")
                message = inner.get("message")

    # If we didn't find an error name in the JSON, try regex on the raw
    # line — covers the case where the JSON is truncated before ``name``.
    if not name:
        m = re.search(r'"name"\s*:\s*"([^"]+)"', s)
        if m:
            name = m.group(1)
    if status is None:
        m = re.search(r'"statusCode"\s*:\s*(\d+)', s)
        if m:
            status = int(m.group(1))
    if not message:
        # Look only inside a responseBody JSON-string (with escaped
        # quotes) — the top-level system prompt also contains a
        # ``"message":"..."`` and we don't want that.
        m = re.search(
            r'\\"type\\":\\"[A-Za-z_]+Error\\",\\"message\\":\\"([^"\\]{1,200})\\"',
            s,
        )
        if m:
            message = m.group(1)

    if not (name or status or provider or model):
        return None

    parts: list[str] = []
    head = name or "opencode error"
    if status:
        head = f"{head} ({status})"
    parts.append(head)
    if provider or model:
        ctx = "/".join(p for p in (provider, model) if p)
        parts.append(f"via {ctx}")
    if message:
        parts.append(f"— {message[:200]}")
    return " ".join(parts)[:400]


_KV_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _extract_kv(s: str, key: str) -> str | None:
    """Pull ``key=value`` (whitespace-terminated) out of a log line."""
    pat = _KV_RE_CACHE.get(key)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(key)}=(\S+)")
        _KV_RE_CACHE[key] = pat
    m = pat.search(s)
    return m.group(1) if m else None


def _try_parse_trailing_json(s: str) -> dict[str, Any] | None:
    """Best-effort parse of a possibly-truncated JSON object at start of ``s``.

    Walks forward looking for the longest balanced-brace prefix that
    parses as JSON. Returns ``None`` if nothing usable.
    """
    if not s.startswith("{"):
        return None
    depth = 0
    in_str = False
    esc = False
    last_close = -1
    for i, ch in enumerate(s):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_close = i
                break
    if last_close == -1:
        return None
    try:
        obj = json.loads(s[: last_close + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _unwrap_response_body(rb: str) -> str | None:
    """Extract a user-readable message from a JSON-encoded responseBody.

    Providers wrap the actual error in JSON like
    ``{"type":"error","error":{"type":"FreeUsageLimitError","message":"..."}}``.
    Walk the parsed object for the deepest ``message`` string.
    """
    try:
        obj = json.loads(rb)
    except (json.JSONDecodeError, ValueError):
        return None

    def _find_message(node: Any, depth: int = 0) -> str | None:
        if depth > 5:
            return None
        if isinstance(node, dict):
            m = node.get("message")
            if isinstance(m, str) and m:
                return m
            for v in node.values():
                found = _find_message(v, depth + 1)
                if found:
                    return found
        elif isinstance(node, list):
            for v in node:
                found = _find_message(v, depth + 1)
                if found:
                    return found
        return None

    return _find_message(obj)


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
                    message = _unwrap_response_body(rb) or rb[:200]
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
