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

import json as _json
import logging
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from agentbox.core.data.jsontypes import RawJson
from agentbox.core.agents import (
    build_prompt,
    engine_load_failure as backend_load_failure,
    list_engines as backends,
)
from agentbox.core.config import load_settings
from agentbox.core.data.constants import RunStatus
from agentbox.core.data import (
    AgentDisabled,
    InvalidRunInput,
    RunNotFound,
    RunnerSnapshot,
    RunSummary,
    now_iso,
    read_transcript,
    UsagePayload,
)
from agentbox.core.data.payload_types import (
    CancelRunResult,
    LogEntry,
    PromptFragmentPayload,
    RerunResult,
    RunCommentsResult,
    RunCreatedResult,
    RunDetailPayload,
    RunDetailResult,
    RunFacetsResult,
    RunnerSnapshotView,
    RunLifecycleResult,
    RunLogsResult,
    RunPromptFragmentsResult,
)
from agentbox.core.data.rows import (
    RunCommentRow,
    SessionRow,
    WebhookDeliveryRow,
)
from agentbox.core.db import AgentDefManager, AgentMetaManager, AgentVersionManager
from agentbox.core.db.runs.run import Run
from agentbox.core.execution.observability.conversation import get as _get_conversation_source
from agentbox.core.execution.orchestrate.executor import RunExecutor
from agentbox.core.execution.orchestrate.setup import NoBackendAvailable
from agentbox.core.data.conversation.transcript import TranscriptSource
from agentbox.core.service.agents import AgentNotFound
from agentbox.core.service.base import Service
from agentbox.core.service.evaluation import EvaluationService

logger = logging.getLogger(__name__)


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

    def list_run_summaries(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[RunSummary]:
        """Recent runs enriched with usage totals, for the ``history ls`` view."""
        return [
            RunSummary(
                id=r.id,
                agent_id=r.agent_id,
                status=r.status,
                created_at=r.created_at,
                finished_at=r.finished_at,
                usage=self.get_usage(r.id),
            )
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

    def get_session(self, session_id: str) -> SessionRow | None:
        """Fetch a session row by ID, return as dict or None."""
        return self._sessions.get_dict(session_id)

    def set_session_workdir(self, session_id: str, workdir: str) -> None:
        """Update the workdir field on a session."""
        self._sessions.set_workdir(session_id, workdir)

    # ══════════════════════════════════════════════════════════════════
    # Usage
    # ══════════════════════════════════════════════════════════════════

    def record_usage(self, run_id: str, payload: UsagePayload) -> None:
        """Upsert usage stats (tokens, cost) for a run (accumulates on conflict)."""
        self._usage.record(run_id, cast(dict[str, Any], payload))

    def get_usage(self, run_id: str) -> UsagePayload | None:
        """Fetch usage row for a run_id, return as dict or None."""
        result = self._usage.get_dict(run_id)
        return cast(UsagePayload | None, result)

    # ══════════════════════════════════════════════════════════════════
    # Comments
    # ══════════════════════════════════════════════════════════════════

    def add_run_comment(self, run_id: str, author: str, body: str) -> RunCommentRow:
        """Insert a comment on a run and return the new row as dict."""
        return self._comments.add(run_id, author, body)

    def list_run_comments(self, run_id: str) -> list[RunCommentRow]:
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

    def list_webhook_deliveries(self, run_id: str) -> list[WebhookDeliveryRow]:
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
    ) -> RunLogsResult:
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
        items: list[LogEntry] = [
            cast(LogEntry, {
                "ts": e.get("ts"),
                "level": e.get("level", "info"),
                "message": e.get("message", ""),
            })
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

    # ══════════════════════════════════════════════════════════════════
    # Run dispatch (from create.py)
    # ══════════════════════════════════════════════════════════════════

    def _assert_enabled(self, agent_meta: AgentMetaManager, agent_id: str) -> None:
        meta = agent_meta.get_meta(agent_id)
        if meta and meta.get("disabled_at"):
            raise AgentDisabled(agent_id, meta.get("disabled_at"))

    async def dispatch_run(
        self,
        agent_id: str,
        *,
        agent_defs: AgentDefManager | None = None,
        agent_meta: AgentMetaManager | None = None,
        executor: RunExecutor,
        input_: str | None = None,
        variables: dict[str, str] | None = None,
        session_id: str | None = None,
        workspace: str | None = None,
        timeout_seconds: int | None = None,
        webhook_url: str | None = None,
        runner: str | None = None,
        backend: str | None = None,
        runner_profile: str | None = None,
        runner_config: dict | None = None,
        runner_embedded: bool = False,
    ) -> RunCreatedResult:
        """Validate input, resolve the agent, and dispatch to the executor.

        ``agent_defs`` and ``agent_meta`` default to ``self._db.*`` when not
        supplied, so route callers need not thread the managers through.

        Raises :class:`AgentNotFound`, :class:`InvalidRunInput`, or
        :class:`NoBackendAvailable`. Returns ``{"run_id", "agent"}``.
        """
        _agent_defs = agent_defs if agent_defs is not None else self._db.agent_defs
        _agent_meta = agent_meta if agent_meta is not None else self._db.agent_meta
        agent = _agent_defs.get(agent_id)
        if agent is None:
            raise AgentNotFound(agent_id)
        self._assert_enabled(_agent_meta, agent.id)

        if input_ is not None and variables is None:
            if agent.composition is not None:
                logger.warning(
                    "run for agent %r uses legacy 'input' but agent has [composition]; "
                    "migrate to 'variables' with 'user_message'",
                    agent.id,
                )
            if webhook_url is not None:
                agent = agent.model_copy(update={"webhook_url": webhook_url})
            composed = build_prompt(
                db=executor.db,
                settings=executor.settings,
                agent=agent,
                input_=input_,
                variables=None,
            )
            run_id = await executor.execute(
                composed,
                variables=None,
                session_id=session_id,
                workspace_override=workspace,
                timeout_seconds=timeout_seconds,
                runner_override=runner,
                backend=backend,
                runner_profile=runner_profile,
                runner_config=runner_config,
            )
            return {"run_id": run_id, "agent": agent.id}

        if variables is None:
            raise InvalidRunInput("either 'input' or 'variables' must be provided")

        if webhook_url is not None:
            agent = agent.model_copy(update={"webhook_url": webhook_url})
        composed = build_prompt(
            db=executor.db,
            settings=executor.settings,
            agent=agent,
            input_="",
            variables=variables,
        )
        run_id = await executor.execute(
            composed,
            variables=variables,
            session_id=session_id,
            workspace_override=workspace,
            timeout_seconds=timeout_seconds,
            runner_override=runner,
            backend=backend,
            runner_profile=runner_profile,
            runner_config=runner_config,
            runner_embedded=runner_embedded,
        )
        return {"run_id": run_id, "agent": agent.id}

    async def rerun(
        self,
        run_id: str,
        *,
        agent_defs: AgentDefManager | None = None,
        agent_meta: AgentMetaManager | None = None,
        executor: RunExecutor,
    ) -> RerunResult:
        """Re-execute a finished run with the same agent + input/variables.

        ``agent_defs`` and ``agent_meta`` default to ``self._db.*`` when not
        supplied, so route callers need not thread the managers through.
        """
        _agent_defs = agent_defs if agent_defs is not None else self._db.agent_defs
        _agent_meta = agent_meta if agent_meta is not None else self._db.agent_meta
        rec = self.get_run(run_id)
        if rec is None:
            raise RunNotFound(run_id)
        agent = _agent_defs.get(rec.agent_id)
        if agent is None:
            raise AgentNotFound(rec.agent_id)
        self._assert_enabled(_agent_meta, agent.id)

        variables: dict[str, str] | None = None
        if rec.variables:
            try:
                parsed = (
                    _json.loads(rec.variables)
                    if isinstance(rec.variables, str)
                    else rec.variables
                )
                if isinstance(parsed, dict):
                    variables = {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                variables = None

        composed = build_prompt(
            db=executor.db,
            settings=executor.settings,
            agent=agent,
            input_=rec.input or "",
            variables=variables,
        )
        new_id = await executor.execute(
            composed,
            variables=variables,
            session_id=None,
            workspace_override=None,
        )
        return {"run_id": new_id, "agent": agent.id, "rerun_of": run_id}

    # ══════════════════════════════════════════════════════════════════
    # Run query (from query.py) — enriched views over the raw list_runs/…
    # ══════════════════════════════════════════════════════════════════

    def _enrich_with_version(
        self, agent_versions: AgentVersionManager, d: Mapping[str, object]
    ) -> dict[str, object]:
        result_dict: dict[str, object] = dict(d)
        vid = d.get("agent_version_id")
        if vid is not None and isinstance(vid, int):
            v = agent_versions.get_by_id(vid)
            result_dict["agent_version"] = v["version"] if v else None
        else:
            result_dict["agent_version"] = None
        return result_dict

    def list_runs_enriched(
        self,
        *,
        agent_versions: AgentVersionManager | None = None,
        agent: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        agent_version: int | None = None,
        q: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
        offset: int = 0,
        paginated: bool = False,
        with_usage: bool = False,
    ) -> list[dict] | dict:
        """Backward-compatible run listing enriched with agent version + usage.

        ``agent_versions`` defaults to ``self._db.agent_versions`` when not
        supplied, so route callers need not thread the manager through.
        """
        _agent_versions = (
            agent_versions if agent_versions is not None else self._db.agent_versions
        )
        if not paginated and not any(
            [status, executor, q, since, until, offset, agent_version]
        ):
            result: list[dict] = [
                self._enrich_with_version(_agent_versions, r)
                for r in self.list_runs(limit=limit, agent_id=agent)
            ]
            if with_usage:
                for d in result:
                    d["usage"] = self.get_usage(d["id"])
            return result
        items, total = EvaluationService().list_runs_paged(
            agent_id=agent,
            status=status,
            executor=executor,
            agent_version=agent_version,
            q=q,
            since_iso=since,
            until_iso=until,
            limit=limit,
            offset=offset,
        )
        enriched = [self._enrich_with_version(_agent_versions, r) for r in items]
        if with_usage:
            for d in enriched:
                d["usage"] = self.get_usage(str(d["id"]))
        return {
            "items": enriched,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < total,
        }

    def run_stats(
        self,
        *,
        agent: str | None = None,
        status: str | None = None,
        executor: str | None = None,
        agent_version: int | None = None,
        q: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ):
        return EvaluationService().stats_for_filters(
            agent_id=agent,
            status=status,
            executor=executor,
            agent_version=agent_version,
            q=q,
            since_iso=since,
            until_iso=until,
        )

    def run_facets(self) -> RunFacetsResult:
        return {
            "agents": EvaluationService().distinct_agent_ids(),
            "executors": EvaluationService().distinct_executors(),
            "statuses": ["ok", "error", "failed", "timeout", "incomplete", "running"],
        }

    def get_run_detail(
        self, run_id: str, *, agent_versions: AgentVersionManager | None = None
    ) -> RunDetailResult:
        """Return the full run detail payload.

        ``agent_versions`` defaults to ``self._db.agent_versions`` when not
        supplied, so route callers need not thread the manager through.
        """
        _agent_versions = (
            agent_versions if agent_versions is not None else self._db.agent_versions
        )
        rec = self.get_run(run_id)
        if rec is None:
            raise RunNotFound(run_id)
        usage = self.get_usage(run_id)
        base_dict = (
            rec.model_dump() if hasattr(rec, "model_dump") else dict(rec.__dict__)
        )

        # Construct RunDetailPayload by building up fields from Run + enrichments
        agent_version: int | None = None
        if rec.agent_version_id is not None:
            ver = _agent_versions.get_by_id(rec.agent_version_id)
            if ver is not None:
                agent_version = ver.get("version")

        snap_raw = base_dict.get("runner_snapshot")
        snap: RunnerSnapshot | None = None
        runner_snapshot: RunnerSnapshotView | None = None
        if isinstance(snap_raw, str) and snap_raw:
            try:
                snap = _json.loads(snap_raw)
                runner_snapshot = snap
            except ValueError:
                runner_snapshot = {"snapshot": "invalid", "raw": snap_raw}
        elif not snap_raw and rec.runner_profile_id:
            runner_snapshot = {"snapshot": "missing"}

        backend: str | None = snap.get("backend") if isinstance(snap, dict) else None
        configured_model: str | None = (
            snap.get("model") if isinstance(snap, dict) else None
        )
        reported_model: str | None = usage.get("model") if usage else None

        # Build the complete RunDetailPayload
        run_payload: RunDetailPayload = {
            "id": base_dict["id"],
            "agent_id": base_dict["agent_id"],
            "session_id": base_dict["session_id"],
            "status": base_dict["status"],
            "input": base_dict["input"],
            "output": base_dict["output"],
            "error": base_dict["error"],
            "workdir": base_dict["workdir"],
            "transcript_path": base_dict["transcript_path"],
            "created_at": base_dict["created_at"],
            "finished_at": base_dict["finished_at"],
            "config_digest": base_dict["config_digest"],
            "agent_version_id": base_dict["agent_version_id"],
            "composition_snapshot": base_dict["composition_snapshot"],
            "rendered_prompt": base_dict["rendered_prompt"],
            "variables": base_dict["variables"],
            "validation_status": base_dict["validation_status"],
            "validation_errors": base_dict["validation_errors"],
            "schema_validated_via": base_dict["schema_validated_via"],
            "post_status": base_dict["post_status"],
            "post_errors": base_dict["post_errors"],
            "conversation_format": base_dict["conversation_format"],
            "conversation_uri": base_dict["conversation_uri"],
            "runner_profile_id": base_dict["runner_profile_id"],
            "resource_snapshot": base_dict["resource_snapshot"],
            "mcp_snapshot": base_dict["mcp_snapshot"],
            "runner_snapshot": runner_snapshot,
            "agent_version": agent_version,
            "backend": backend,
            "configured_model": configured_model,
            "reported_model": reported_model,
            "prompt_version_id": base_dict["prompt_version_id"],
        }
        return {"run": run_payload, "usage": usage}

    def get_run_prompt_fragments(self, run_id: str) -> RunPromptFragmentsResult:
        rec = self.get_run(run_id)
        if rec is None:
            raise RunNotFound(run_id)
        raw = self.get_run_prompt(run_id)
        fragments_list = _json.loads(raw) if raw else []
        total = sum(
            int(sb)
            for f in fragments_list
            if isinstance(sb := f.get("size_bytes"), (int, float))
        )
        # The fragments are created by capture_fragments() which produces
        # properly-structured PromptFragmentPayload dicts from JSON.
        fragments: list[PromptFragmentPayload] = [
            {
                "name": f["name"],
                "source": f["source"],
                "injected_by": f["injected_by"],
                "content": f["content"],
                "inspectable": f["inspectable"],
                "size_bytes": f["size_bytes"],
            }
            for f in fragments_list
        ]
        return {"run_id": run_id, "fragments": fragments, "total_bytes": total}

    # ══════════════════════════════════════════════════════════════════
    # Run lifecycle from external workers (from lifecycle.py)
    # ══════════════════════════════════════════════════════════════════

    def complete_run(
        self,
        run_id: str,
        *,
        agent_defs: AgentDefManager | None = None,
        ok: bool,
        output: str | None,
        error: str | None,
        usage: UsagePayload | None,
        schedule_webhook_cb: Any = None,
    ) -> RunLifecycleResult:
        """Finalize a run from an external worker.

        ``agent_defs`` defaults to ``self._db.agent_defs`` when not supplied,
        so route callers need not thread the manager through.
        """
        _agent_defs = agent_defs if agent_defs is not None else self._db.agent_defs
        existing = self.get_run(run_id)
        if existing is None:
            raise RunNotFound(run_id)
        if existing.status not in {"ok", "error"}:
            self.finish_run(run_id, ok=ok, output=output, error=error)
        if usage:
            try:
                self.record_usage(run_id, usage)
            except Exception as exc:
                logger.warning("record_usage failed for %s: %s", run_id, exc)

        refreshed = self.get_run(run_id) or existing
        if schedule_webhook_cb is not None:
            agent = _agent_defs.get(refreshed.agent_id)
            schedule_webhook_cb(agent, refreshed)
        return {"ok": True, "run_id": run_id, "status": refreshed.status}

    def snapshot_run(
        self,
        run_id: str,
        *,
        agent_defs: AgentDefManager | None = None,
        rendered_prompt: dict,
        variables: dict,
        response_raw: str,
        validation_status: str = "ok",
        validation_errors: list[str] | None = None,
        composition_snapshot: dict | None = None,
        schedule_webhook_cb: Any = None,
    ) -> RunLifecycleResult:
        """Store a snapshot for an embedded run; idempotent on terminal runs.

        ``agent_defs`` defaults to ``self._db.agent_defs`` when not supplied,
        so route callers need not thread the manager through.
        """
        _agent_defs = agent_defs if agent_defs is not None else self._db.agent_defs
        existing = self.get_run(run_id)
        if existing is None:
            raise RunNotFound(run_id)
        if existing.rendered_prompt is not None:
            logger.warning("snapshot_run: overwriting existing snapshot for %s", run_id)

        self.save_run_snapshot(
            run_id=run_id,
            rendered_prompt=rendered_prompt,
            variables=variables,
            validation_status=validation_status,
            validation_errors=validation_errors or [],
            composition_snapshot=composition_snapshot,
        )

        if existing.status not in {"ok", "error"}:
            self.finish_run(
                run_id,
                ok=validation_status != "fail",
                output=response_raw,
                error=None if validation_status != "fail" else "validation failed",
            )

        refreshed = self.get_run(run_id) or existing
        if schedule_webhook_cb is not None:
            agent = _agent_defs.get(refreshed.agent_id)
            if agent is not None:
                schedule_webhook_cb(agent, refreshed)
        return {"ok": True, "run_id": run_id}

    def post_outcome(
        self,
        run_id: str,
        *,
        status: str,
        error_kind: str | None = None,
        errors: list[dict] | None = None,
    ) -> RunLifecycleResult:
        existing = self.get_run(run_id)
        if existing is None:
            raise RunNotFound(run_id)
        self.set_run_post_outcome(
            run_id, ok=(status == "ok"), error_kind=error_kind, errors=errors
        )
        refreshed = self.get_run(run_id) or existing
        return {"ok": True, "run_id": run_id, "post_status": refreshed.post_status}

    async def cancel_run(
        self,
        run_id: str,
        *,
        executor: RunExecutor,
    ) -> CancelRunResult:
        """Cancel an in-progress run. Idempotent on terminal runs."""
        existing = self.get_run(run_id)
        if existing is None:
            raise RunNotFound(run_id)
        if not RunStatus(existing.status).is_running:
            return {"run_id": run_id, "cancelled": False, "status": existing.status}
        cancelled = await executor.cancel_run(run_id)
        refreshed = self.get_run(run_id) or existing
        return {"run_id": run_id, "cancelled": cancelled, "status": refreshed.status}

    # ══════════════════════════════════════════════════════════════════
    # Comments (from feedback.py) + transcript file read (from stream.py)
    # ══════════════════════════════════════════════════════════════════

    def list_comments(self, run_id: str) -> RunCommentsResult:
        if self.get_run(run_id) is None:
            raise RunNotFound(run_id)
        return {"run_id": run_id, "comments": self.list_run_comments(run_id)}

    def add_comment(self, run_id: str, *, author: str, body: str) -> RunCommentRow:
        if self.get_run(run_id) is None:
            raise RunNotFound(run_id)
        return self.add_run_comment(run_id, author, body)

    def read_transcript_events(self, run_id: str) -> list[RawJson]:
        """Read the JSONL transcript file for a run as a list of event dicts.

        Returns arbitrary backend-emitted events (structure varies by backend).
        Each event is a JSON dict with at minimum a 'type' key.
        """
        rec = self.get_run(run_id)
        if rec is None or not rec.transcript_path:
            raise RunNotFound(run_id)
        return read_transcript(Path(rec.transcript_path))


def no_backend_detail(exc: NoBackendAvailable) -> str:
    """Compose an honest 'why is no backend available' message."""
    loaded = set(backends().keys())
    parts: list[str] = []
    for name in exc.attempted:
        failure = backend_load_failure(name)
        if failure is not None:
            parts.append(f"{name!r} failed to load at startup: {failure}")
        elif name not in loaded:
            parts.append(f"{name!r} is not a registered backend")
        else:
            parts.append(f"{name!r} failed to instantiate")
    why = "; ".join(parts) if parts else "no backend candidates were derived"
    return (
        f"agent {exc.agent_id!r}: cannot dispatch — {why}. "
        f"Registered backends: {sorted(loaded)}."
    )
