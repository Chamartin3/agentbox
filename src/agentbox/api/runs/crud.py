"""/runs endpoints — create, fetch, stream.

Thin HTTP layer: handlers parse the request, delegate to
``core.service.runs``, and translate domain errors to ``HTTPException``.
The WebSocket stream remains here because it owns the transport.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from agentbox.core.data.jsontypes import RawJson
from agentbox.api.deps import get_execution_service, get_executor
from agentbox.api.runs.schemas import (
    CompleteRunBody,
    CreateRunBody,
    PostOutcomeBody,
    RunCommentBody,
    RunRatingBody,
    SnapshotBody,
)
from agentbox.api.runs.webhooks import schedule_webhook
from agentbox.core.data.payload_types import (
    CancelRunResult,
    PaginatedRunsResult,
    RunCommentsResult,
    RunCreatedResult,
    RunDetailResult,
    RunFacetsResult,
    RunLifecycleResult,
    RunPromptFragmentsResult,
)
from agentbox.core.data.rows import RunCommentRow, RunStatsRow
from agentbox.core.service import read_transcript, NoBackendAvailable
from agentbox.core.service.agents import AgentNotFound
from agentbox.core.service.execution import ExecutionService, no_backend_detail as _svc_no_backend_detail
from agentbox.core.data import AgentDisabled, InvalidRunInput, RunNotFound

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
async def create_run(body: CreateRunBody) -> RunCreatedResult:
    try:
        return await get_execution_service().dispatch_run(
            body.agent,
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
            fresh_workspace=body.fresh_workspace,
            session_mode=body.session_mode,
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
) -> list[RawJson] | PaginatedRunsResult:
    """List runs. See ``ExecutionService.list_runs_enriched`` for the shape."""
    result = ExecutionService().list_runs_enriched(
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
    if isinstance(result, dict):
        return {
            "items": result["items"],
            "total": result["total"],
            "offset": result["offset"],
            "limit": result["limit"],
            "has_more": result["has_more"],
        }
    return result


@router.get("/_stats")
def runs_stats(
    agent: str | None = None,
    status: str | None = None,
    executor: str | None = None,
    agent_version: int | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> RunStatsRow:
    """Aggregated stats for the run dashboard."""
    return ExecutionService().run_stats(
        agent=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since=since,
        until=until,
    )


@router.post("/{run_id}/complete")
async def complete_run(run_id: str, body: CompleteRunBody) -> RunLifecycleResult:
    try:
        return get_execution_service().complete_run(
            run_id,
            ok=body.ok,
            output=body.output,
            error=body.error,
            usage=body.usage,
            schedule_webhook_cb=schedule_webhook,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/snapshot")
async def snapshot_run(run_id: str, body: SnapshotBody) -> RunLifecycleResult:
    try:
        return get_execution_service().snapshot_run(
            run_id,
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
def post_outcome(run_id: str, body: PostOutcomeBody) -> RunLifecycleResult:
    """Record downstream post-processing outcome for a completed run."""
    try:
        return ExecutionService().post_outcome(
            run_id,
            status=body.status,
            error_kind=body.error_kind,
            errors=body.errors,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/rerun")
async def rerun(run_id: str) -> RunCreatedResult:
    """Re-execute a finished run with the same agent + input/variables."""
    try:
        return await get_execution_service().rerun(
            run_id,
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
def list_comments(run_id: str) -> RunCommentsResult:
    try:
        return ExecutionService().list_comments(run_id)
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/comments")
def add_comment(run_id: str, body: RunCommentBody) -> RunCommentRow:
    try:
        return ExecutionService().add_comment(
            run_id, author=body.author, body=body.body
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.put("/{run_id}/rating")
def set_run_rating(run_id: str, body: RunRatingBody) -> dict:
    """Set the run's 0-5 star rating."""
    try:
        ExecutionService().set_run_rating(run_id, body.rating)
        return {"rating": body.rating}
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/{run_id}/rating")
def clear_run_rating(run_id: str) -> dict:
    """Clear the run's rating."""
    try:
        ExecutionService().set_run_rating(run_id, None)
        return {"rating": None}
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str) -> CancelRunResult:
    """Cancel an in-progress run. Idempotent."""
    try:
        return await ExecutionService().cancel_run(run_id, executor=get_executor())
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.get("/_facets")
def run_facets() -> RunFacetsResult:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    return ExecutionService().run_facets()


@router.get("/{run_id}")
def get_run(run_id: str) -> RunDetailResult:
    try:
        return get_execution_service().get_run_detail(run_id)
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{run_id}/prompt")
def get_run_prompt(run_id: str) -> RunPromptFragmentsResult:
    try:
        return ExecutionService().get_run_prompt_fragments(run_id)
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{run_id}/transcript")
def get_transcript(run_id: str) -> list[RawJson]:
    """Read the JSONL transcript file for a run.

    Returns a list of backend-emitted events (structure varies by backend).
    """
    try:
        return ExecutionService().read_transcript_events(run_id)
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.websocket("/{run_id}/stream")
async def stream_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    broadcaster = get_executor().broadcaster(run_id)
    if broadcaster is None:
        # Replay transcript from disk if run is already finished.
        rec = get_execution_service().get_run(run_id)
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
