"""Locate and parse Claude CLI JSONL session logs.

The Claude CLI persists a per-session JSONL log under
``$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/<session-uuid>.jsonl``. Each line
is a typed entry (``user``, ``assistant``, ``system``, ``attachment``, ...)
that captures the full conversation including ``thinking`` blocks, ``tool_use``
calls, ``stop_reason``, and per-turn ``usage``.

agentbox launches Claude CLI with a per-run ``cwd=/data/runs/<random-id>``;
that cwd is logged as the first transcript event. This module:

1. Reads the agentbox transcript to recover the per-run cwd.
2. Encodes it to Claude's project-dir convention (``/`` → ``-``).
3. Returns the newest ``*.jsonl`` under that project dir.
4. Parses the JSONL into a compact turn summary suitable for inspection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def encode_cwd(cwd: str) -> str:
    """Convert ``/data/runs/abc`` → ``-data-runs-abc`` (Claude CLI convention)."""
    return cwd.replace("/", "-")


def extract_run_cwd(transcript_path: Path) -> str | None:
    """Scan the agentbox transcript JSONL for the ``cwd=`` log line."""
    if not transcript_path.exists():
        return None
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message", "")
        if isinstance(msg, str) and "cwd=" in msg:
            cwd = msg.split("cwd=", 1)[1].rstrip(")").strip()
            return cwd
    return None


def find_session_log(transcript_path: Path, claude_projects_root: Path) -> Path | None:
    """Locate the Claude CLI session log for a given agentbox run.

    Returns the most recently modified ``*.jsonl`` under the run's project
    dir, or ``None`` if the cwd is missing or no log exists yet.
    """
    cwd = extract_run_cwd(transcript_path)
    if not cwd:
        return None
    project_dir = claude_projects_root / encode_cwd(cwd)
    if not project_dir.is_dir():
        return None
    candidates = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


@dataclass
class ContentPart:
    type: str
    length: int
    body: str | None = None
    tool_name: str | None = None
    tool_input: Any | None = None


@dataclass
class Turn:
    index: int
    role: str
    ts: str | None
    stop_reason: str | None = None
    usage: dict[str, Any] | None = None
    content: list[ContentPart] = field(default_factory=list)


@dataclass
class ConversationSummary:
    session_id: str | None
    log_path: str
    turns: list[Turn]
    totals: dict[str, Any]


def _summarize_content(items: Any, include_bodies: bool) -> list[ContentPart]:
    parts: list[ContentPart] = []
    if not isinstance(items, list):
        if isinstance(items, str):
            parts.append(
                ContentPart(
                    type="text",
                    length=len(items),
                    body=items if include_bodies else None,
                )
            )
        return parts
    for c in items:
        if not isinstance(c, dict):
            continue
        t = c.get("type", "?")
        if t == "text":
            body = c.get("text", "") or ""
            parts.append(
                ContentPart(
                    type=t, length=len(body), body=body if include_bodies else None
                )
            )
        elif t == "thinking":
            body = c.get("thinking", "") or ""
            parts.append(
                ContentPart(
                    type=t, length=len(body), body=body if include_bodies else None
                )
            )
        elif t == "tool_use":
            tool_input = c.get("input")
            parts.append(
                ContentPart(
                    type=t,
                    length=len(json.dumps(tool_input)) if tool_input is not None else 0,
                    tool_name=c.get("name"),
                    tool_input=tool_input if include_bodies else None,
                )
            )
        elif t == "tool_result":
            content = c.get("content")
            body = json.dumps(content) if not isinstance(content, str) else content
            parts.append(
                ContentPart(
                    type=t, length=len(body), body=body if include_bodies else None
                )
            )
        else:
            parts.append(ContentPart(type=t, length=0))
    return parts


def parse_session_log(
    path: Path,
    include_bodies: bool = False,
    roles: set[str] | None = None,
) -> ConversationSummary:
    """Parse a Claude CLI session log into a turn-by-turn summary.

    ``include_bodies=True`` includes the full text/thinking/tool bodies.
    ``roles`` filters to a subset (default: user, assistant, system).
    """
    if roles is None:
        roles = {"user", "assistant", "system"}
    turns: list[Turn] = []
    session_id: str | None = None
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "thinking_chars": 0,
        "text_chars": 0,
        "stop_max_tokens": 0,
        "stop_end_turn": 0,
    }
    if not path.exists():
        return ConversationSummary(
            session_id=None, log_path=str(path), turns=[], totals=totals
        )
    idx = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session_id is None:
            session_id = entry.get("sessionId") or entry.get("session_id")
        role = entry.get("type")
        if role not in roles:
            continue
        ts = entry.get("timestamp")
        msg = entry.get("message", {})
        usage = msg.get("usage") if isinstance(msg, dict) else None
        stop_reason = msg.get("stop_reason") if isinstance(msg, dict) else None
        content_raw = (
            msg.get("content") if isinstance(msg, dict) else entry.get("content")
        )
        parts = _summarize_content(content_raw, include_bodies)
        if usage:
            totals["input_tokens"] += int(usage.get("input_tokens") or 0)
            totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            totals["cache_read_tokens"] += int(
                usage.get("cache_read_input_tokens") or 0
            )
            totals["cache_creation_tokens"] += int(
                usage.get("cache_creation_input_tokens") or 0
            )
        for p in parts:
            if p.type == "thinking":
                totals["thinking_chars"] += p.length
            elif p.type == "text":
                totals["text_chars"] += p.length
        if stop_reason == "max_tokens":
            totals["stop_max_tokens"] += 1
        elif stop_reason == "end_turn":
            totals["stop_end_turn"] += 1
        turns.append(
            Turn(
                index=idx,
                role=role,
                ts=ts,
                stop_reason=stop_reason,
                usage=usage,
                content=parts,
            )
        )
        idx += 1
    return ConversationSummary(
        session_id=session_id,
        log_path=str(path),
        turns=turns,
        totals=totals,
    )
