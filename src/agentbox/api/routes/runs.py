"""/runs endpoints — create, fetch, stream."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agentbox.api.deps import get_executor, get_loader, get_store
from agentbox.api.webhooks import schedule_webhook
from agentbox.core.data import read_transcript

router = APIRouter(prefix="/api/runs", tags=["runs"])


class CreateRunBody(BaseModel):
    agent: str
    input: str | None = None
    """Legacy free-text input. Mutually exclusive with ``variables``."""

    variables: dict[str, str] | None = None
    """Variable map for prompt composition. Required when the agent
    declares a ``[composition]`` block."""

    session_id: str | None = None
    workspace: str | None = None
    """Optional workspace override (named workspace or explicit path)."""

    timeout_seconds: int | None = None
    """Per-run timeout override. Overrides the agent's ``runner.timeout_seconds``
    for this invocation only."""

    webhook_url: str | None = None
    """Per-run webhook URL override. Overrides the agent's ``webhook_url``
    for this invocation only. Set to empty string to suppress the webhook."""

    runner: str | None = None
    """Per-run runner kind override (deprecated — use ``backend``).
    Overrides the agent's ``runner.kind`` for this invocation only."""

    backend: str | None = None
    """Per-run backend override. Overrides the agent's backend selection
    for this invocation only. E.g. ``"claude_code"``, ``"opencode"``,
    ``"token"``."""

    runner_profile: str | None = None
    """Per-run runner profile ID. Selects a named profile to resolve the
    effective runner configuration. Takes precedence over agent defaults."""

    runner_config: dict[str, Any] | None = None
    """Per-run runner configuration dict. Inline config overrides; merged
    with or superseeds profile-based settings."""

    runner_embedded: bool = False
    """When ``True``, the caller will run the agent itself (e.g. pydantic-ai
    in-process) and POST a snapshot back via ``/runs/{run_id}/snapshot``."""


@router.post("")
async def create_run(body: CreateRunBody) -> dict:
    import logging

    logger = logging.getLogger(__name__)
    loader = get_loader()
    store = get_store()
    agent = store.get_agent_def(body.agent) or loader.get(body.agent)
    if agent is None:
        raise HTTPException(404, f"unknown agent {body.agent!r}")

    # Legacy grace period: warn when using old string input
    if body.input is not None and body.variables is None:
        if agent.composition is not None:
            logger.warning(
                "run for agent %r uses legacy 'input' but agent has [composition]; "
                "migrate to 'variables' with 'user_message'",
                agent.id,
            )
        executor = get_executor()
        try:
            run_id = await executor.execute(
                agent,
                body.input,
                session_id=body.session_id,
                workspace_override=body.workspace,
                timeout_seconds=body.timeout_seconds,
                webhook_url=body.webhook_url,
                runner_override=body.runner,
                backend=body.backend,
                runner_profile=body.runner_profile,
                runner_config=body.runner_config,
            )
        except KeyError as exc:
            if exc.args and exc.args[0] == "NO_BACKEND_AVAILABLE":
                raise HTTPException(
                    422,
                    f"no backend registered for agent {agent.id!r} "
                    f"(runner.kind={agent.runner.kind!r}). "
                    "Promote a version with a supported runner via the agentbox UI.",
                ) from exc
            raise
        return {"run_id": run_id, "agent": agent.id}

    if body.variables is None:
        raise HTTPException(422, "either 'input' or 'variables' must be provided")

    executor = get_executor()
    try:
        run_id = await executor.execute(
            agent,
            "",  # input is derived from composition
            variables=body.variables,
            session_id=body.session_id,
            workspace_override=body.workspace,
            timeout_seconds=body.timeout_seconds,
            webhook_url=body.webhook_url,
            runner_override=body.runner,
            backend=body.backend,
            runner_profile=body.runner_profile,
            runner_config=body.runner_config,
            runner_embedded=body.runner_embedded,
        )
    except KeyError as exc:
        # `_select_backend` raises KeyError("NO_BACKEND_AVAILABLE") when the
        # agent's runner.kind has no registered adapter (e.g. legacy
        # `pydantic_ai` after that backend was removed). Surface this as a
        # structured 422 so callers can render a useful message instead of
        # a bare HTML 500.
        if exc.args and exc.args[0] == "NO_BACKEND_AVAILABLE":
            raise HTTPException(
                422,
                f"no backend registered for agent {agent.id!r} "
                f"(runner.kind={agent.runner.kind!r}). "
                "Promote a version with a supported runner via the agentbox UI.",
            ) from exc
        raise
    return {"run_id": run_id, "agent": agent.id}


@router.get("")
def list_runs(
    agent: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
    paginated: bool = False,
) -> list[dict] | dict:
    """List runs.

    Backward-compatible shape: by default returns the raw list. Pass
    ``paginated=true`` (or any filter beyond ``agent``+``limit``) to get
    the envelope ``{items, total, offset, limit, has_more}``.
    """
    store = get_store()

    def _enrich(rec) -> dict:
        d = rec.__dict__.copy()
        vid = d.get("agent_version_id")
        if vid is not None:
            v = store.get_version_by_id(vid)
            d["agent_version"] = v["version"] if v else None
        else:
            d["agent_version"] = None
        return d

    if not paginated and not any([status, executor, q, since, until, offset]):
        return [_enrich(r) for r in store.list_runs(limit=limit, agent_id=agent)]
    items, total = store.list_runs_paged(
        agent_id=agent,
        status=status,
        executor=executor,
        q=q,
        since_iso=since,
        until_iso=until,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_enrich(r) for r in items],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }


class CompleteRunBody(BaseModel):
    """Payload posted by an external worker that ran the agent.

    The worker (typically the consumer's own backend, talking back via
    the HTTP runner kick-off pattern) calls this when it knows the
    terminal outcome of a run that's currently ``running`` in agentbox.
    """

    ok: bool
    output: str | None = None
    error: str | None = None
    usage: dict | None = None


@router.post("/{run_id}/complete")
async def complete_run(run_id: str, body: CompleteRunBody) -> dict:
    """Finalize a run from an external worker.

    Calls ``finish_run`` (flipping status to ok/error), optionally
    records usage, and fires the agent's webhook if one is configured.
    Idempotent on the run state: re-finalising already-finished runs is
    a no-op for status but will re-fire the webhook (consumers must
    treat webhook delivery as at-least-once).
    """
    store = get_store()
    existing = store.get_run(run_id)
    if existing is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    if existing.status not in {"ok", "error"}:
        store.finish_run(run_id, ok=body.ok, output=body.output, error=body.error)
    if body.usage:
        try:
            store.record_usage(run_id, body.usage)
        except Exception as exc:
            # Usage is supplementary — never fail the finalisation on it.
            import logging

            logging.getLogger(__name__).warning(
                "record_usage failed for %s: %s", run_id, exc
            )

    refreshed = store.get_run(run_id) or existing
    loader = get_loader()
    agent = store.get_agent_def(refreshed.agent_id) or loader.get(refreshed.agent_id)
    schedule_webhook(agent, refreshed, store)
    return {"ok": True, "run_id": run_id, "status": refreshed.status}


class SnapshotBody(BaseModel):
    """Payload posted by a caller after running an embedded agent."""

    rendered_prompt: dict
    variables: dict
    response_raw: str
    validation_status: str = "ok"
    validation_errors: list[str] = []
    composition_snapshot: dict | None = None


@router.post("/{run_id}/snapshot")
async def snapshot_run(run_id: str, body: SnapshotBody) -> dict:
    """Store a snapshot for an embedded run.

    Idempotent: a second snapshot for the same run_id replaces the first
    and logs a warning.
    """
    import logging

    logger = logging.getLogger(__name__)
    store = get_store()
    existing = store.get_run(run_id)
    if existing is None:
        raise HTTPException(404, f"unknown run {run_id!r}")

    if existing.rendered_prompt is not None:
        logger.warning("snapshot_run: overwriting existing snapshot for %s", run_id)

    store.save_run_snapshot(
        run_id=run_id,
        rendered_prompt=body.rendered_prompt,
        variables=body.variables,
        validation_status=body.validation_status,
        validation_errors=body.validation_errors,
        composition_snapshot=body.composition_snapshot,
    )

    # Also finalize the run if not already terminal
    if existing.status not in {"ok", "error"}:
        store.finish_run(
            run_id,
            ok=body.validation_status != "fail",
            output=body.response_raw,
            error=None if body.validation_status != "fail" else "validation failed",
        )

    refreshed = store.get_run(run_id) or existing
    loader = get_loader()
    agent = loader.get(refreshed.agent_id)
    if agent:
        schedule_webhook(agent, refreshed, store)

    return {"ok": True, "run_id": run_id}


class PostOutcomeBody(BaseModel):
    status: str
    error_kind: str | None = None
    errors: list[dict] | None = None


@router.post("/{run_id}/post_outcome")
def post_outcome(run_id: str, body: PostOutcomeBody) -> dict:
    """Record downstream post-processing outcome for a completed run."""
    store = get_store()
    existing = store.get_run(run_id)
    if existing is None:
        raise HTTPException(404, f"unknown run {run_id!r}")

    ok = body.status == "ok"
    store.set_run_post_outcome(
        run_id,
        ok=ok,
        error_kind=body.error_kind,
        errors=body.errors,
    )
    refreshed = store.get_run(run_id) or existing
    return {
        "ok": True,
        "run_id": run_id,
        "post_status": refreshed.post_status,
    }


@router.post("/{run_id}/rerun")
async def rerun(run_id: str) -> dict:
    """Re-execute a finished run with the same agent + input/variables.

    Returns the new run id. The original run is not modified.
    """
    import json as _json

    store = get_store()
    rec = store.get_run(run_id)
    if rec is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    loader = get_loader()
    agent = store.get_agent_def(rec.agent_id) or loader.get(rec.agent_id)
    if agent is None:
        raise HTTPException(404, f"agent {rec.agent_id!r} no longer exists")

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

    executor = get_executor()
    new_id = await executor.execute(
        agent,
        rec.input or "",
        variables=variables,
        session_id=None,
        workspace_override=None,
    )
    return {"run_id": new_id, "agent": agent.id, "rerun_of": run_id}


class RunCommentBody(BaseModel):
    author: str = "api"
    body: str


@router.get("/{run_id}/comments")
def list_comments(run_id: str) -> dict:
    store = get_store()
    if store.get_run(run_id) is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    return {"run_id": run_id, "comments": store.list_run_comments(run_id)}


@router.post("/{run_id}/comments")
def add_comment(run_id: str, body: RunCommentBody) -> dict:
    store = get_store()
    if store.get_run(run_id) is None:
        raise HTTPException(404, f"unknown run {run_id!r}")
    return store.add_run_comment(run_id, body.author, body.body)


@router.get("/_facets")
def run_facets() -> dict:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    store = get_store()
    return {
        "agents": store.distinct_agent_ids(),
        "executors": store.distinct_executors(),
        "statuses": ["ok", "error", "running"],
    }


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    rec = get_store().get_run(run_id)
    if rec is None:
        raise HTTPException(404)
    usage = get_store().get_usage(run_id)
    guardrails = get_store().list_guardrails(run_id)
    run_dict = dict(rec.__dict__)
    if rec.agent_version_id is not None:
        ver = get_store().get_version_by_id(rec.agent_version_id)
        if ver is not None:
            run_dict["agent_version"] = ver.get("version")
    return {"run": run_dict, "usage": usage, "guardrails": guardrails}


@router.get("/{run_id}/prompt")
def get_run_prompt(run_id: str) -> dict:
    import json as _json

    rec = get_store().get_run(run_id)
    if rec is None:
        raise HTTPException(404)
    raw = get_store().get_run_prompt(run_id)
    fragments = _json.loads(raw) if raw else []
    total = sum(int(f.get("size_bytes") or 0) for f in fragments)
    return {"run_id": run_id, "fragments": fragments, "total_bytes": total}


@router.get("/{run_id}/transcript")
def get_transcript(run_id: str) -> list[dict]:
    rec = get_store().get_run(run_id)
    if rec is None or not rec.transcript_path:
        raise HTTPException(404)
    return read_transcript(Path(rec.transcript_path))


@router.websocket("/{run_id}/stream")
async def stream_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    broadcaster = get_executor().broadcaster(run_id)
    if broadcaster is None:
        # Replay transcript from disk if run is already finished.
        rec = get_store().get_run(run_id)
        if rec is None or not rec.transcript_path:
            await ws.close(code=4404)
            return
        for ev in read_transcript(Path(rec.transcript_path)):
            await ws.send_json(ev)
        await ws.close()
        return

    queue = broadcaster.subscribe()
    try:
        while True:
            ev = await queue.get()
            if ev is None:
                break
            await ws.send_json(ev.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    finally:
        await ws.close()
