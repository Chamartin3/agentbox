"""ExecutionService — run lifecycle, sessions, usage, comments, webhooks,
prompts, and snapshots.

This service consolidates all execution-domain persistence. It extends
``Service`` (self-wiring Database from settings) and delegates pure-DB
operations to the per-entity managers under ``self._db``.

ponytail: multi-table operations (e.g. create_run + prompt capture) are
non-atomic across managers — each manager opens its own transaction.
Partial writes are self-healing (orphan reaper at startup cleans up
unfinished runs). Only accept this as long as we're single-process SQLite.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from agentbox.core.config import load_settings
from agentbox.core.constants import RunStatus
from agentbox.core.data import now_iso, read_transcript, RunnerSnapshot
from agentbox.core.db.models.runs.run import Run
from agentbox.core.execution.observability.conversation import get as _get_conversation_source
from agentbox.core.data.conversation.transcript import TranscriptSource
from agentbox.core.service.base import Service


class ExecutionService(Service):
    """Run lifecycle, sessions, usage, comments, webhooks, prompts, and snapshots.
    
    Usage::

        svc = ExecutionService()
        run_id = svc.create_run("agent-1", "input", "/tmp/wd", "/tmp/t.jsonl")
        svc.finish_run(run_id, ok=True, output="result")
    """

    def __init__(self) -> None:
        super().__init__()
        self._runs = self._db.runs
        self._sessions = self._db.sessions
        self._usage = self._db.usage
        self._comments = self._db.run_comments
        self._webhooks = self._db.webhook_deliveries
        self._prompts = self._db.run_prompts

    # ══════════════════════════════════════════════════════════════════
    # Run lifecycle
    # ══════════════════════════════════════════════════════════════════

    def create_run(
        self,
        agent_id: str,
        input_: str,
        workdir: str,
        transcript_path: str,
        session_id: str | None = None,
        config_digest: str | None = None,
        runner_profile_id: str | None = None,
    ) -> str:
        """Insert a new run row (status=running) and return the UUID hex run_id."""
        rid = uuid.uuid4().hex
        self._runs.create(
            id=rid,
            agent_id=agent_id,
            session_id=session_id,
            status=RunStatus.RUNNING.value,
            input=input_,
            workdir=workdir,
            transcript_path=transcript_path,
            created_at=now_iso(),
            config_digest=config_digest,
            runner_profile_id=runner_profile_id,
        )
        return rid

    def finish_run(
        self,
        run_id: str,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
        status: str | None = None,
        validation_status: str | None = None,
        validation_errors: list[str] | None = None,
        schema_validated_via: str | None = None,
    ) -> None:
        """Mark a running run as finished with optional validation fields."""
        self._runs.finish_full(
            run_id=run_id,
            ok=ok,
            output=output,
            error=error,
            status=status,
            validation_status=validation_status,
            validation_errors=validation_errors,
            schema_validated_via=schema_validated_via,
        )

    def set_run_conversation(
        self,
        run_id: str,
        conversation_format: str | None,
        conversation_uri: str | None = None,
    ) -> None:
        """Persist the conversation format and optional URI for a run."""
        self._runs.set_conversation(run_id, conversation_format, conversation_uri)

    def set_run_post_outcome(
        self,
        run_id: str,
        ok: bool,
        error_kind: str | None = None,
        errors: list[dict] | None = None,
    ) -> None:
        """Set post-run outcome status on a run row."""
        self._runs.set_post_outcome(run_id, ok, error_kind, errors)

    def list_orphaned_unnotified_runs(self) -> list[dict]:
        """Return runs whose error contains 'orphaned' and have no post_status."""
        return [r.model_dump() for r in self._runs.list_orphaned_unnotified()]

    def reap_orphan_runs(self) -> int:
        """Mark all ``running`` rows as ``incomplete``. Returns count."""
        return self._runs.reap_orphans()

    def set_run_status(self, run_id: str, status: str) -> None:
        """Directly set the status column on a run row."""
        self._runs.set_status(run_id, status)

    def get_run(self, run_id: str) -> Run | None:
        """Fetch a single run by ID, return the Run model or None."""
        return self._runs.get(run_id)

    def list_runs(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[dict]:
        """List recent runs (optionally filtered by agent_id)."""
        return [
            r.model_dump()
            for r in self._runs.list_runs_by_agent(limit=limit, agent_id=agent_id)
        ]

    # ══════════════════════════════════════════════════════════════════
    # Sessions
    # ══════════════════════════════════════════════════════════════════

    def create_session(
        self, agent_id: str, mode: str, workdir: str | None
    ) -> str:
        """Insert a new session row and return its UUID hex session_id."""
        return self._sessions.create_session(agent_id, mode, workdir)

    def touch_session(self, session_id: str) -> None:
        """Update last_used_at to now for the given session."""
        self._sessions.touch(session_id)

    def get_session(self, session_id: str) -> dict | None:
        """Fetch a session row by ID, return as dict or None."""
        return self._sessions.get_dict(session_id)

    def set_session_workdir(self, session_id: str, workdir: str) -> None:
        """Update the workdir field on a session."""
        self._sessions.set_workdir(session_id, workdir)

    # ══════════════════════════════════════════════════════════════════
    # Usage
    # ══════════════════════════════════════════════════════════════════

    def record_usage(self, run_id: str, payload: dict) -> None:
        """Upsert usage stats (tokens, cost) for a run (accumulates on conflict)."""
        self._usage.record(run_id, payload)

    def get_usage(self, run_id: str) -> dict | None:
        """Fetch usage row for a run_id, return as dict or None."""
        return self._usage.get_dict(run_id)

    # ══════════════════════════════════════════════════════════════════
    # Comments
    # ══════════════════════════════════════════════════════════════════

    def add_run_comment(self, run_id: str, author: str, body: str) -> dict:
        """Insert a comment on a run and return the new row as dict."""
        return self._comments.add(run_id, author, body)

    def list_run_comments(self, run_id: str) -> list[dict]:
        """List all comments for a run ordered by created_at."""
        return self._comments.list_for_run(run_id)

    # ══════════════════════════════════════════════════════════════════
    # Webhooks
    # ══════════════════════════════════════════════════════════════════

    def record_webhook_delivery(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """Insert a webhook delivery attempt log row."""
        self._webhooks.record(
            run_id=run_id,
            attempt=attempt,
            url=url,
            payload=payload,
            response_status=response_status,
            response_body=response_body,
            latency_ms=latency_ms,
            error=error,
        )

    def list_webhook_deliveries(self, run_id: str) -> list[dict]:
        """List all webhook delivery attempts for a run."""
        return self._webhooks.list_for_run(run_id)

    # ══════════════════════════════════════════════════════════════════
    # Transcript helpers (moved from tool bodies in plan 106_01)
    # ══════════════════════════════════════════════════════════════════

    def get_transcript(self, run_id: str, limit: int, offset: int) -> dict:
        """Paginated JSONL transcript for a run.

        Returns ``{items, total, limit, offset, has_more}``.  Items are raw
        event dicts decoded from the JSONL file.
        """
        rec = self._runs.get(run_id)
        if rec is None or not rec.transcript_path:
            return {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False,
            }
        data_dir = load_settings().data_dir
        events = read_transcript(Path(rec.transcript_path), data_dir)
        total = len(events)
        page = events[offset : offset + limit]
        return {
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(page) < total,
        }

    def get_logs(
        self, run_id: str, level: str | None, limit: int, offset: int
    ) -> dict:
        """Log events from the transcript for a run.

        Filters to ``type == "log"`` events, optionally further filtered by
        *level*.  Returns lightweight ``{ts, level, message}`` rows.
        """
        rec = self._runs.get(run_id)
        if rec is None or not rec.transcript_path:
            return {
                "items": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False,
            }
        data_dir = load_settings().data_dir
        events = read_transcript(Path(rec.transcript_path), data_dir)
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

    # ══════════════════════════════════════════════════════════════════
    # Prompts
    # ══════════════════════════════════════════════════════════════════

    def save_run_prompt(self, run_id: str, fragments_json: str) -> None:
        """Upsert the prompt fragments JSON for a run."""
        self._prompts.save(run_id, fragments_json)

    def get_run_prompt(self, run_id: str) -> str | None:
        """Fetch the fragments column for a run_id; return raw JSON string or None."""
        return self._prompts.get_fragments(run_id)

    # ══════════════════════════════════════════════════════════════════
    # Snapshots
    # ══════════════════════════════════════════════════════════════════

    def save_run_snapshot(
        self,
        run_id: str,
        rendered_prompt: dict,
        variables: dict,
        validation_status: str,
        validation_errors: list[str],
        composition_snapshot: dict | None = None,
    ) -> None:
        """Persist the full post-run snapshot onto the run row."""
        self._runs.save_snapshot(
            run_id=run_id,
            rendered_prompt=rendered_prompt,
            variables=variables,
            validation_status=validation_status,
            validation_errors=validation_errors,
            composition_snapshot=composition_snapshot,
        )

    def save_run_composition(
        self,
        run_id: str,
        composition_snapshot: dict | None,
        rendered_prompt: dict | None,
        variables: dict | None,
    ) -> None:
        """Persist only composition/prompt/variables fields (partial update)."""
        self._runs.save_composition(
            run_id=run_id,
            composition_snapshot=composition_snapshot,
            rendered_prompt=rendered_prompt,
            variables=variables,
        )

    def save_resource_snapshots(
        self,
        run_id: str,
        *,
        resource_snapshot: list[dict] | None = None,
        mcp_snapshot: dict | None = None,
    ) -> None:
        """Persist resource snapshot and/or MCP snapshot JSON onto the run row."""
        self._runs.save_resource_snapshots(
            run_id,
            resource_snapshot=resource_snapshot,
            mcp_snapshot=mcp_snapshot,
        )

    def save_run_runner_snapshot(
        self,
        run_id: str,
        runner_snapshot: RunnerSnapshot,
    ) -> None:
        """Persist the runner config snapshot (append-only, writes only if null)."""
        self._runs.save_runner_snapshot(run_id, runner_snapshot)

    # ══════════════════════════════════════════════════════════════════
    # Conversation
    # ══════════════════════════════════════════════════════════════════

    def load_conversation(
        self,
        run: Any,
        conversation_format: str | None,
        *,
        include_bodies: bool,
        offset: int,
        limit: int,
    ) -> tuple[Any | None, str | None]:
        """Load a run's runner-native conversation, falling back to the JSONL transcript.

        Returns ``(view, fallback_reason)``. ``fallback_reason`` is None when
        the runner-native source produced turns, otherwise the reason the
        fallback fired (``"no_native_source"`` / ``"native_empty"``). When the
        JSONL transcript itself is missing, returns ``(None, None)`` so the
        caller can surface ``no_conversation``.
        """
        native_view = None
        if conversation_format is not None:
            try:
                src_cls = _get_conversation_source(conversation_format)
            except KeyError:
                src_cls = None
            if src_cls is not None:
                src = src_cls.for_run(run)
                if src is not None:
                    native_view = src.load(
                        include_bodies=include_bodies, offset=offset, limit=limit
                    )
                    if native_view.turns:
                        return native_view, None

        fb_src = TranscriptSource.for_run(run)
        if fb_src is None:
            return native_view, None
        fb_view = fb_src.load(
            include_bodies=include_bodies, offset=offset, limit=limit
        )
        reason = "native_empty" if native_view is not None else "no_native_source"
        return fb_view, reason
