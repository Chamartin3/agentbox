"""Run cancellation logic extracted from RunExecutor."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from pathlib import Path
from typing import Any

from agentbox.core.config import Settings
from agentbox.core.constants import LogLevel, RunStatus
from agentbox.core.events import DoneEvent, LogEvent
from agentbox.core.data import AgentDef, RunRecord
from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster

logger = logging.getLogger(__name__)


def cancel_run(
    *,
    run_id: str,
    db: Any,
    broadcasters: dict[str, "RunBroadcaster"],
    run_tasks: dict[str, asyncio.Task[None]],
    settings: Settings,
) -> bool:
    """Cancel an in-progress run."""
    task = run_tasks.get(run_id)
    if task is None or task.done():
        return False

    error_msg = "cancelled by operator"
    try:
        db.runs.finish_full(
            run_id,
            ok=False,
            error=error_msg,
            status=RunStatus.INCOMPLETE.value,
        )
    except Exception:
        logger.exception(
            "cancel_run: failed to persist incomplete status for %s", run_id
        )

    broadcaster = broadcasters.get(run_id)
    if broadcaster is not None:
        with contextlib.suppress(Exception):
            broadcaster.publish(
                LogEvent(run_id=run_id, level=LogLevel.WARN, message=error_msg)
            )
            broadcaster.publish(
                DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=error_msg,
                    status=RunStatus.ERROR,
                )
            )

    task.cancel()
    try:
        refreshed_run = db.runs.get(run_id)
        if refreshed_run is not None:
            agent: Any | None = None
            try:
                _agent = db.agent_defs.get(refreshed_run.agent_id)
                if isinstance(_agent, AgentDef):
                    agent = _agent
            except Exception:
                logger.exception(
                    "cancel dispatch: failed to resolve agent for run %s", run_id
                )
            transcript_path = (
                Path(refreshed_run.transcript_path)
                if refreshed_run.transcript_path
                else None
            )
            _record_fields = {f.name for f in dataclasses.fields(RunRecord)}
            refreshed = RunRecord(**{
                k: v for k, v in refreshed_run.model_dump().items()
                if k in _record_fields
            })
            dispatch_completion(
                run=refreshed,
                agent=agent,
                store=_RunDispatchAdapter(db),
                broadcaster=broadcaster,
                transcript_path=transcript_path,
                settings=settings,
            )
    except Exception:
        logger.exception("cancel dispatch failed for %s", run_id)
    return True


class _RunDispatchAdapter:
    """Minimal DispatchStore adapter backed by Database managers."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_run(self, run_id: str) -> Any:
        return self._db.runs.get(run_id)

    def set_run_status(self, run_id: str, status: str) -> None:
        self._db.runs.set_status(run_id, status)

    def get_usage(self, run_id: str) -> dict | None:
        return self._db.usage.get_dict(run_id)

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
        self._db.webhook_deliveries.record(
            run_id,
            attempt,
            url,
            payload=payload,
            response_status=response_status,
            response_body=response_body,
            latency_ms=latency_ms,
            error=error,
        )
