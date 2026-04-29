"""MCP tools for run inspection."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastmcp import FastMCP

from agentbox.core.conversations import get as get_conversation_source
from agentbox.core.conversations.sources.transcript import TranscriptSource
from agentbox.core.data.transcripts import read_transcript
from agentbox.mcp_server.deps import get_context
from agentbox.mcp_server.schemas import clamp_limit


def _serialize(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def get_run(run_id: str) -> dict:
        """Get a single run record (status, input, output, errors, timing)."""
        store = get_context().store
        rec = store.get_run(run_id)
        if rec is None:
            return {"error": "not_found", "run_id": run_id}
        usage = store.get_usage(run_id)
        return {"run": _serialize(rec), "usage": usage}

    @mcp.tool
    def list_runs(
        agent_id: str | None = None,
        status: str | None = None,
        model: str | None = None,
        q: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Paginated list of runs with optional filters.

        ``model`` filters by executor/model name. ``q`` is a substring
        match against input/output/error/id. ``since``/``until`` are
        ISO-8601 timestamps."""
        limit = clamp_limit(limit)
        store = get_context().store
        rows, total = store.list_runs_paged(
            agent_id=agent_id,
            status=status,
            executor=model,
            q=q,
            since_iso=since,
            until_iso=until,
            limit=limit,
            offset=offset,
        )
        items = [_serialize(r) for r in rows]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }

    @mcp.tool
    def get_run_transcript(run_id: str, limit: int = 200, offset: int = 0) -> dict:
        """Paginated slice of the JSONL transcript for a run."""
        limit = clamp_limit(limit)
        store = get_context().store
        rec = store.get_run(run_id)
        if rec is None or not rec.transcript_path:
            return {"items": [], "total": 0, "limit": limit, "offset": offset,
                    "has_more": False}
        from pathlib import Path
        events = read_transcript(Path(rec.transcript_path), get_context().settings.data_dir)
        total = len(events)
        page = events[offset : offset + limit]
        return {
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
        }

    @mcp.tool
    def get_run_conversation(
        run_id: str,
        include_bodies: bool = False,
        turn_offset: int = 0,
        turn_limit: int = 50,
    ) -> dict:
        """Parsed session log for a run (runner-agnostic).

        Returns per-turn ``role``, ``ts``, ``stop_reason``, ``usage``, and a
        compact ``content`` summary listing each part's type and char length
        (e.g. ``thinking(35511c)``, ``text(3804c)``, ``tool_use:mcp__...``).
        This is the right tool for diagnosing slow/timed-out runs without
        pulling tens of KB into the conversation.

        Pass ``include_bodies=True`` to inline full ``text``/``thinking``/
        ``tool_use`` bodies. Use ``turn_offset``/``turn_limit`` to page when
        there are many turns.
        """
        ctx = get_context()
        rec = ctx.store.get_run(run_id)
        if rec is None or not rec.transcript_path:
            return {"error": "not_found", "run_id": run_id}

        # Dispatch on conversation_format. When the format is not set
        # (pre-migration rows or backends without native logs), fall
        # back to the agentbox JSONL transcript.
        fmt = getattr(rec, "conversation_format", None)
        turn_limit = clamp_limit(turn_limit)
        view, fallback_used = _load_conversation_with_fallback(
            rec,
            fmt,
            include_bodies=include_bodies,
            offset=turn_offset,
            limit=turn_limit,
        )
        if view is None:
            return {
                "error": "no_conversation",
                "run_id": run_id,
                "format": fmt,
                "uri": getattr(rec, "conversation_uri", None),
            }
        return {
            "run_id": run_id,
            "session_id": view.session_id,
            "source_format": view.source_format,
            "source_uri": view.source_uri,
            "totals": {
                "input_tokens": view.totals.input_tokens,
                "output_tokens": view.totals.output_tokens,
                "cache_read_tokens": view.totals.cache_read_tokens,
                "cache_write_tokens": view.totals.cache_write_tokens,
                "thinking_chars": view.totals.thinking_chars,
                "text_chars": view.totals.text_chars,
                "stop_max_tokens": view.totals.stop_max_tokens,
                "stop_end_turn": view.totals.stop_end_turn,
            },
            "total_turns": len(view.turns),
            "turn_offset": turn_offset,
            "turn_limit": turn_limit,
            "turns": [
                {
                    "index": t.index,
                    "role": t.role,
                    "ts": t.ts,
                    "stop_reason": t.stop_reason,
                    "usage": t.usage,
                    "content": [
                        {k: v for k, v in p.__dict__.items() if v is not None}
                        for p in t.content
                    ],
                }
                for t in view.turns
            ],
        }

    @mcp.tool
    def get_run_logs(
        run_id: str,
        level: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        """Log events emitted during a run.

        Filters the transcript to ``type == "log"`` events (the
        ``LogEvent`` envelope — typically stderr lines from the agent
        process and executor-side warnings). Use ``level`` to filter to
        a specific level: ``debug``, ``info``, ``warn``, or ``error``.

        Returns lightweight ``{ts, level, message}`` rows so a caller can
        page through stderr without pulling tool calls or full text
        events into context. For everything (text, tool calls, usage,
        guardrail, done) use ``get_run_transcript``.
        """
        limit = clamp_limit(limit)
        store = get_context().store
        rec = store.get_run(run_id)
        if rec is None or not rec.transcript_path:
            return {"items": [], "total": 0, "limit": limit, "offset": offset,
                    "has_more": False}
        from pathlib import Path
        events = read_transcript(Path(rec.transcript_path), get_context().settings.data_dir)
        logs = [e for e in events if e.get("type") == "log"]
        if level:
            logs = [e for e in logs if e.get("level") == level]
        total = len(logs)
        page = logs[offset : offset + limit]
        items = [
            {
                "ts": e.get("ts"),
                "level": e.get("level", "info"),
                "message": e.get("message", ""),
            }
            for e in page
        ]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }

    @mcp.tool
    def get_run_webhook_deliveries(run_id: str) -> dict:
        """Webhook delivery attempts for a run (each attempt is one row)."""
        store = get_context().store
        rec = store.get_run(run_id)
        if rec is None:
            return {"error": "not_found", "run_id": run_id}
        items = store.list_webhook_deliveries(run_id)
        return {"run_id": run_id, "items": items, "total": len(items)}

    @mcp.tool
    def get_run_usage(run_id: str) -> dict:
        """Token + cost breakdown for a single run."""
        usage = get_context().store.get_usage(run_id)
        return usage or {"error": "not_found", "run_id": run_id}

    @mcp.tool
    def get_run_output(run_id: str) -> dict:
        """Final output payload for a run (without surrounding metadata)."""
        rec = get_context().store.get_run(run_id)
        if rec is None:
            return {"error": "not_found", "run_id": run_id}
        return {"run_id": run_id, "output": rec.output, "status": rec.status}

    @mcp.tool
    def get_run_errors(run_id: str) -> dict:
        """Error + validation errors for a failed run."""
        rec = get_context().store.get_run(run_id)
        if rec is None:
            return {"error": "not_found", "run_id": run_id}
        return {
            "run_id": run_id,
            "status": rec.status,
            "error": rec.error,
            "validation_status": getattr(rec, "validation_status", None),
            "validation_errors": getattr(rec, "validation_errors", None),
        }
