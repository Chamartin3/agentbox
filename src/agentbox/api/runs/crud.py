"""/runs endpoints — create, fetch, stream.

Thin HTTP layer: handlers parse the request, delegate to
``core.service.runs``, and translate domain errors to ``HTTPException``.
The WebSocket stream remains here because it owns the transport.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agentbox.api.deps import get_executor, get_loader, get_store
from agentbox.api.webhooks import schedule_webhook
from agentbox.core.data import read_transcript
from agentbox.core.service.execution import runs as runs_service
from agentbox.core.service.execution.runs import (
    AgentNotFound,
    InvalidRunInput,
    NoBackendAvailable,
    RunNotFound,
)

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
    try:
        return await runs_service.create_run(
            body.agent,
            store=get_store(),
            executor=get_executor(),
            loader=get_loader(),
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
    except InvalidRunInput as exc:
        raise HTTPException(422, str(exc)) from exc
    except NoBackendAvailable as exc:
        raise HTTPException(503, runs_service.no_backend_detail(exc)) from exc


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
    """List runs. See ``core.service.runs.list_runs`` for the shape."""
    return runs_service.list_runs(
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
    return runs_service.run_stats(
        store=get_store(),
        agent=agent,
        status=status,
        executor=executor,
        agent_version=agent_version,
        q=q,
        since=since,
        until=until,
    )


class CompleteRunBody(BaseModel):
    """Payload posted by an external worker that ran the agent."""

    ok: bool
    output: str | None = None
    error: str | None = None
    usage: dict | None = None


@router.post("/{run_id}/complete")
async def complete_run(run_id: str, body: CompleteRunBody) -> dict:
    try:
        return runs_service.complete_run(
            run_id,
            store=get_store(),
            ok=body.ok,
            output=body.output,
            error=body.error,
            usage=body.usage,
            loader=get_loader(),
            schedule_webhook_cb=schedule_webhook,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


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
    try:
        return runs_service.snapshot_run(
            run_id,
            store=get_store(),
            rendered_prompt=body.rendered_prompt,
            variables=body.variables,
            response_raw=body.response_raw,
            validation_status=body.validation_status,
            validation_errors=body.validation_errors,
            composition_snapshot=body.composition_snapshot,
            loader=get_loader(),
            schedule_webhook_cb=schedule_webhook,
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


class PostOutcomeBody(BaseModel):
    status: str
    error_kind: str | None = None
    errors: list[dict] | None = None


@router.post("/{run_id}/post_outcome")
def post_outcome(run_id: str, body: PostOutcomeBody) -> dict:
    """Record downstream post-processing outcome for a completed run."""
    try:
        return runs_service.post_outcome(
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
        return await runs_service.rerun(
            run_id,
            store=get_store(),
            executor=get_executor(),
            loader=get_loader(),
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc
    except AgentNotFound as exc:
        raise HTTPException(
            404, f"agent {exc.agent_id!r} no longer exists"
        ) from exc


class RunCommentBody(BaseModel):
    author: str = "api"
    body: str


@router.get("/{run_id}/comments")
def list_comments(run_id: str) -> dict:
    try:
        return runs_service.list_comments(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/comments")
def add_comment(run_id: str, body: RunCommentBody) -> dict:
    try:
        return runs_service.add_comment(
            run_id, store=get_store(), author=body.author, body=body.body
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict:
    """Cancel an in-progress run. Idempotent."""
    try:
        return await runs_service.cancel_run(
            run_id, store=get_store(), executor=get_executor()
        )
    except RunNotFound as exc:
        raise HTTPException(404, f"unknown run {exc.run_id!r}") from exc


@router.get("/_facets")
def run_facets() -> dict:
    """Distinct values for filter dropdowns (agents, executors, statuses)."""
    return runs_service.run_facets(store=get_store())


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return runs_service.get_run_detail(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{run_id}/prompt")
def get_run_prompt(run_id: str) -> dict:
    try:
        return runs_service.get_run_prompt(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404) from exc


@router.get("/{run_id}/transcript")
def get_transcript(run_id: str) -> list[dict]:
    try:
        return runs_service.get_transcript(run_id, store=get_store())
    except RunNotFound as exc:
        raise HTTPException(404) from exc


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
