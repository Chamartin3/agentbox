"""Run lifecycle — complete, snapshot, post_outcome, cancel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agentbox.core.service.agents import resolve_agent
from agentbox.core.service.execution.service import ExecutionService
from agentbox.core.service.execution.types import RunNotFound

from agentbox.core.constants import RunStatus

if TYPE_CHECKING:
    from agentbox.core.db import SessionStore
    from agentbox.core.execution.orchestrate.executor import RunExecutor

logger = logging.getLogger(__name__)


def _svc() -> ExecutionService:
    return ExecutionService()


def complete_run(
    run_id: str,
    *,
    store: SessionStore,
    ok: bool,
    output: str | None,
    error: str | None,
    usage: dict | None,
    schedule_webhook_cb: Any = None,
) -> dict:
    """Finalize a run from an external worker."""
    svc = _svc()
    existing = svc.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    if existing.status not in {"ok", "error"}:
        svc.finish_run(run_id, ok=ok, output=output, error=error)
    if usage:
        try:
            svc.record_usage(run_id, usage)
        except Exception as exc:
            logger.warning("record_usage failed for %s: %s", run_id, exc)

    refreshed = svc.get_run(run_id) or existing
    if schedule_webhook_cb is not None:
        agent = resolve_agent(refreshed.agent_id, store=store)
        schedule_webhook_cb(agent, refreshed, store)
    return {"ok": True, "run_id": run_id, "status": refreshed.status}


def snapshot_run(
    run_id: str,
    *,
    store: SessionStore,
    rendered_prompt: dict,
    variables: dict,
    response_raw: str,
    validation_status: str = "ok",
    validation_errors: list[str] | None = None,
    composition_snapshot: dict | None = None,
    schedule_webhook_cb: Any = None,
) -> dict:
    """Store a snapshot for an embedded run; idempotent on terminal runs."""
    svc = _svc()
    existing = svc.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    if existing.rendered_prompt is not None:
        logger.warning("snapshot_run: overwriting existing snapshot for %s", run_id)

    svc.save_run_snapshot(
        run_id=run_id,
        rendered_prompt=rendered_prompt,
        variables=variables,
        validation_status=validation_status,
        validation_errors=validation_errors or [],
        composition_snapshot=composition_snapshot,
    )

    if existing.status not in {"ok", "error"}:
        svc.finish_run(
            run_id,
            ok=validation_status != "fail",
            output=response_raw,
            error=None if validation_status != "fail" else "validation failed",
        )

    refreshed = svc.get_run(run_id) or existing
    if schedule_webhook_cb is not None:
        agent = resolve_agent(refreshed.agent_id, store=store)
        if agent is not None:
            schedule_webhook_cb(agent, refreshed, store)
    return {"ok": True, "run_id": run_id}


def post_outcome(
    run_id: str,
    *,
    store: SessionStore,
    status: str,
    error_kind: str | None = None,
    errors: list[dict] | None = None,
) -> dict:
    svc = _svc()
    existing = svc.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    svc.set_run_post_outcome(
        run_id, ok=(status == "ok"), error_kind=error_kind, errors=errors
    )
    refreshed = svc.get_run(run_id) or existing
    return {"ok": True, "run_id": run_id, "post_status": refreshed.post_status}


async def cancel_run(
    run_id: str,
    *,
    store: SessionStore,
    executor: RunExecutor,
) -> dict:
    """Cancel an in-progress run. Idempotent on terminal runs."""
    svc = _svc()
    existing = svc.get_run(run_id)
    if existing is None:
        raise RunNotFound(run_id)
    if not RunStatus(existing.status).is_running:
        return {"run_id": run_id, "cancelled": False, "status": existing.status}
    cancelled = await executor.cancel_run(run_id)
    refreshed = svc.get_run(run_id) or existing
    return {"run_id": run_id, "cancelled": cancelled, "status": refreshed.status}
