"""/runs endpoints — create, fetch, stream.

Thin HTTP layer: handlers parse the request, delegate to
``core.service.runs``, and translate domain errors to ``HTTPException``.
The WebSocket stream remains here because it owns the transport.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from agentbox.api.deps import get_db, get_executor, get_store
from agentbox.api.runs.schemas import (
    CompleteRunBody,
    CreateRunBody,
    PostOutcomeBody,
    RunCommentBody,
    SnapshotBody,
)
from agentbox.api.runs.webhooks import schedule_webhook
from agentbox.core.service import read_transcript, NoBackendAvailable
from agentbox.core.service.execution import (
    add_comment as _svc_add_comment,
    AgentNotFound,
    cancel_run as _svc_cancel_run,
    complete_run as _svc_complete_run,
    create_run as _svc_create_run,
    get_run_detail as _svc_get_run_detail,
    get_run_prompt as _svc_get_run_prompt,
    get_transcript as _svc_get_transcript,
    InvalidRunInput,
    list_comments as _svc_list_comments,
    list_runs as _svc_list_runs,
    no_backend_detail as _svc_no_backend_detail,
    post_outcome as _svc_post_outcome,
    rerun as _svc_rerun,
    run_facets as _svc_run_facets,
    run_stats as _svc_run_stats,
    snapshot_run as _svc_snapshot_run,
)
from agentbox.core.service.execution.types import AgentDisabled, RunNotFound

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
async def create_run(body: CreateRunBody) -> dict:
    try:
        return await _svc_create_run(
            body.agent,
            store=get_store(),
            executor=get_executor(),
            input_=body.input,
            variables=body.variables,
            session_id=body.session_id,
            workspace=body.workspace,
            timeout_seconds=body.timeout_seconds,
            webhook_url=body.webhook_url,
            runner=body.runner,
            backend=body.backend,
            runner_profile=body.runner_profile,
            runner_config=body.runner_config,
            runner_embedded=body.runner_embedded,
        )
    except AgentNotFound as exc:
        raise HTTPException(404, f"unknown agent {exc.agent_id!r}") from exc
    except AgentDisabled as exc:
        raise HTTPException(
            403,
            {
                "code": "agent_disabled",
                "detail": str(exc),
                "agent_id": exc.agent_id,
                "disabled_at": exc.disabled_at,
            },
        ) from exc
    except InvalidRunInput as exc:
        raise HTTPException(422, str(exc)) from exc
    except NoBackendAvailable as exc:
        raise HTTPException(503, _svc_no_backend_detail(exc)) from exc


@router.get("")
def list_runs(
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
) -> list[dict] | dict:
    """List runs. See ``core.service._svc_list_runs`` for the shape."""
    return _svc_list_runs(
        store=get_store(),
        agent=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        paginated=paginated,
    )


@router.get("/_stats")
def runs_stats(
    agent: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    agent_version: int | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """Aggregated stats for the run dashboard."""
    return _svc_run_stats(
        store=get_store(),
        agent=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since=since,
        until=until,
    )


@router.post("/{run_id}/complete")
async def complete_run(run_id: str, body: CompleteRunBody) -> dict:
    try:
        return _svc_complete_run(
            run_id,
            store=get_store(),
            ok=body.ok,
            output=body.output,
            error=body.error,
            usage=body.usage,
            schedule_webhook_cb=schedule_webhook,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/snapshot")
async def snapshot_run(run_id: str, body: SnapshotBody) -> dict:
    try:
        return _svc_snapshot_run(
            run_id,
            store=get_store(),
            rendered_prompt=body.rendered_prompt,
            variables=body.variables,
            response_raw=body.response_raw,
            validation_status=body.validation_status,
            validation_errors=body.validation_errors,
            composition_snapshot=body.composition_snapshot,
            schedule_webhook_cb=schedule_webhook,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/post_outcome")
def post_outcome(run_id: str, body: PostOutcomeBody) -> dict:
    """Record downstream post-processing outcome for a completed run."""
    try:
        return _svc_post_outcome(
            run_id,
            store=get_store(),
            status=body.status,
            error_kind=body.error_kind,
            errors=body.errors,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/rerun")
async def rerun(run_id: str) -> dict:
    """Re-execute a finished run with the same agent + input/variables."""
    try:
        return await _svc_rerun(
            run_id,
            store=get_store(),
            executor=get_executor(),
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc
    except AgentNotFound as exc:
        raise HTTPException(404, f"agent {exc.agent_id!r} no longer exists") from exc
    except AgentDisabled as exc:
        raise HTTPException(
            403,
            {
                "code": "agent_disabled",
                "detail": str(exc),
                "agent_id": exc.agent_id,
                "disabled_at": exc.disabled_at,
            },
        ) from exc


@router.get("/{run_id}/comments")
def list_comments(run_id: str) -> dict:
    try:
        return _svc_list_comments(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/comments")
def add_comment(run_id: str, body: RunCommentBody) -> dict:
    try:
        return _svc_add_comment(
            run_id, store=get_store(), author=body.author, body=body.body
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    """Cancel an in-progress run. Idempotent."""
    try:
        return await _svc_cancel_run(run_id, store=get_store(), executor=get_executor())
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.get("/_facets")
def run_facets() -> dict:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    return _svc_run_facets(store=get_store())


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return _svc_get_run_detail(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{run_id}/prompt")
def get_run_prompt(run_id: str) -> dict:
    try:
        return _svc_get_run_prompt(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{run_id}/transcript")
def get_transcript(run_id: str) -> list[dict]:
    try:
        return _svc_get_transcript(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.websocket("/{run_id}/stream")
async def stream_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    broadcaster = get_executor().broadcaster(run_id)
    if broadcaster is None:
        # Replay transcript from disk if run is already finished.
        rec = get_db().runs.get(run_id)
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
