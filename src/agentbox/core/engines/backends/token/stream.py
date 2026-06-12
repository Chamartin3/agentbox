"""Streaming + pydantic-ai event adaptation helpers for ``TokenBackend``.

Splits two concerns out of the main backend:

* :class:`_RefSection` / :class:`TokenDeps` — the reference payload
  carried through pydantic-ai's ``RunContext`` so the static system
  prompt stays small.
* ``_iter_message_history_events`` / ``_emit_message_history`` — adapt
  a pydantic-ai ``all_messages()`` history into the agentbox
  :class:`RunEvent` envelope vocabulary.
* :func:`_format_provider_error` — convert pydantic-ai / provider
  exceptions into a single error string that's safe to surface in a
  ``DoneEvent``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agentbox.core.constants import LogLevel, MessageRole
from agentbox.core.data import (
    LogEvent,
    RunEvent,
    TextEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)

try:
    from pydantic_ai.exceptions import UnexpectedModelBehavior as _UnexpectedModelBehavior
except Exception:
    _UnexpectedModelBehavior = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class _RefSection:
    heading: str
    content: str


@dataclass(frozen=True)
class TokenDeps:
    """Runtime deps injected into pydantic-ai's ``RunContext``.

    Reference documents (markdown, skills, attached resources) ride
    through deps rather than being concatenated into the system prompt
    string. A dynamic ``@system_prompt`` reads ``ctx.deps.references``
    and renders the headings inline — this keeps the *base* system
    prompt small and lets the same backend handle agents with very
    different reference payloads without rebuilding the prompt string.
    """

    references: tuple[_RefSection, ...] = ()


def _format_provider_error(exc: Exception, *, model: str, provider: str | None) -> str:
    raw = str(exc)
    if isinstance(exc, ValidationError) and "finish_reason" in raw and "error" in raw:
        provider_name = provider or "unknown"
        return (
            f"OpenRouter/{provider_name} returned finish_reason='error' "
            f"for model={model} (upstream provider failure). Raw: {raw}"
        )

    if _UnexpectedModelBehavior is not None and isinstance(exc, _UnexpectedModelBehavior):
        body = getattr(exc, "body", None)
        if body:
            return f"agent execution error: {exc}; body: {body}"

    return f"agent execution error: {exc}"


def _part_kind(part: Any) -> str:
    explicit = getattr(part, "part_kind", None) or getattr(part, "kind", None)
    if explicit:
        return str(explicit)
    return part.__class__.__name__.lower()


def _stringify_excerpt(value: Any, *, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str)
        except Exception:
            text = str(value)
    return text[:limit]


def _iter_message_history_events(run_id: str, messages: Any) -> list[RunEvent]:
    events: list[RunEvent] = []
    for msg in messages or []:
        msg_kind = getattr(msg, "kind", "") or msg.__class__.__name__.lower()
        is_response = "response" in msg_kind or "model" in msg_kind
        for part in getattr(msg, "parts", []) or []:
            kind = _part_kind(part)
            if is_response and ("text" in kind and "tool" not in kind):
                text = getattr(part, "content", None) or getattr(part, "text", None)
                if text:
                    events.append(
                        TextEvent(run_id=run_id, role=MessageRole.ASSISTANT, text=str(text))
                    )
                continue
            if "thinking" in kind or "reasoning" in kind:
                text = (
                    getattr(part, "text", None)
                    or getattr(part, "content", None)
                    or getattr(part, "reasoning", None)
                )
                if text:
                    events.append(ThinkingEvent(run_id=run_id, text=str(text)))
                continue

            if "tool-call" in kind or "tool_call" in kind or "toolcall" in kind:
                tool = getattr(part, "tool_name", None) or getattr(part, "name", "")
                args = getattr(part, "args", None) or getattr(part, "arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                if not isinstance(args, dict):
                    args = {"value": args}
                call_id = (
                    getattr(part, "tool_call_id", None)
                    or getattr(part, "call_id", None)
                    or getattr(part, "id", None)
                )
                events.append(
                    ToolCallEvent(
                        run_id=run_id,
                        tool=str(tool),
                        arguments=args,
                        call_id=str(call_id) if call_id is not None else None,
                    )
                )
                continue

            if (
                "tool-return" in kind
                or "tool_return" in kind
                or "tool-result" in kind
                or "tool_result" in kind
                or "toolreturn" in kind
            ):
                tool = getattr(part, "tool_name", None) or getattr(part, "name", "")
                content = getattr(part, "content", None)
                call_id = (
                    getattr(part, "tool_call_id", None)
                    or getattr(part, "call_id", None)
                    or getattr(part, "id", None)
                )
                ok = not bool(getattr(part, "is_error", False))
                if content is not None and hasattr(content, "success"):
                    ok = bool(content.success)
                events.append(
                    ToolResultEvent(
                        run_id=run_id,
                        tool=str(tool),
                        call_id=str(call_id) if call_id is not None else None,
                        ok=ok,
                        result_excerpt=_stringify_excerpt(content),
                    )
                )
    return events


def _emit_message_history(run_id: str, messages: Any) -> list[RunEvent]:
    try:
        return _iter_message_history_events(run_id, messages)
    except Exception as exc:
        result: list[RunEvent] = [
            LogEvent(
                run_id=run_id,
                level=LogLevel.WARN,
                message=f"could not emit pydantic-ai message history: {exc}",
            )
        ]
        return result
