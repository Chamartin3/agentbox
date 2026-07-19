"""Run cancellation logic extracted from RunExecutor."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from pathlib import Path
from typing import Any, cast

from agentbox.core.config import Settings
from agentbox.core.data import UsagePayload
from agentbox.core.data.constants import LogLevel, RunStatus
from agentbox.core.data.events import DoneEvent, LogEvent
from agentbox.core.data import AgentDef, RunRecord
from agentbox.core.db import (
    AgentDefManager,
    RunManager,
    UsageManager,
    WebhookDeliveryManager,
)
from agentbox.core.execution.dispatch import dispatch_completion
from agentbox.core.execution.observability.stream.broadcaster import RunBroadcaster

logger = logging.getLogger(__name__)


def cancel_run(
    *,
    run_id: str,
    runs: RunManager,
    agent_defs: AgentDefManager,
    usage: UsageManager,
    webhook_deliveries: WebhookDeliveryManager,
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
        runs.finish_full(
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
        refreshed_run = runs.get(run_id)
        if refreshed_run is not None:
            agent: Any | None = None
            try:
                _agent = agent_defs.get(refreshed_run.agent_id)
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
                store=_RunDispatchAdapter(
                    runs=runs, usage=usage, webhook_deliveries=webhook_deliveries
                ),
                broadcaster=broadcaster,
                transcript_path=transcript_path,
                settings=settings,
            )
    except Exception:
        logger.exception("cancel dispatch failed for %s", run_id)
    return True


class _RunDispatchAdapter:
    """Minimal DispatchStore adapter backed by specific managers."""

    def __init__(
        self,
        *,
        runs: RunManager,
        usage: UsageManager,
        webhook_deliveries: WebhookDeliveryManager,
    ) -> None:
        self._runs = runs
        self._usage = usage
        self._webhook_deliveries = webhook_deliveries

    def get_run(self, run_id: str) -> Any:
        return self._runs.get(run_id)

    def set_run_status(self, run_id: str, status: str) -> None:
        self._runs.set_status(run_id, status)

    def get_usage(self, run_id: str) -> UsagePayload | None:
        # UsageRow and UsagePayload are structurally equivalent at runtime;
        # cast bridges the minor TypedDict field variance difference.
        return cast(UsagePayload, row) if (row := self._usage.get_dict(run_id)) is not None else None

    def record_webhook_delivery(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict[str, Any] | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        self._webhook_deliveries.record(
            run_id,
            attempt,
            url,
            payload=payload,
            response_status=response_status,
            response_body=response_body,
            latency_ms=latency_ms,
            error=error,
        )
