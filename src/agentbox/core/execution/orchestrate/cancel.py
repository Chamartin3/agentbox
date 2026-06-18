"""Run cancellation logic extracted from RunExecutor."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.config import Settings
from agentbox.core.constants import LogLevel, RunStatus
from agentbox.core.db import AgentDef, DoneEvent, LogEvent
from agentbox.core.execution.dispatch import dispatch_completion

if TYPE_CHECKING:
    from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster
    from agentbox.core.db import RunStore

logger = logging.getLogger(__name__)


def cancel_run(
    *,
    run_id: str,
    store: RunStore,
    broadcasters: dict[str, RunBroadcaster],
    run_tasks: dict[str, asyncio.Task[None]],
    settings: Settings,
) -> bool:
    """Cancel an in-progress run."""
    task = run_tasks.get(run_id)
    if task is None or task.done():
        return False

    error_msg = "cancelled by operator"
    try:
        store.finish_run(
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
        refreshed = store.get_run(run_id)
        if refreshed is not None:
            agent: Any | None = None
            try:
                _agent = store.get_agent_def(refreshed.agent_id)
                if isinstance(_agent, AgentDef):
                    agent = _agent
            except Exception:
                logger.exception(
                    "cancel dispatch: failed to resolve agent for run %s", run_id
                )
            transcript_path = (
                Path(refreshed.transcript_path)
                if refreshed.transcript_path
                else None
            )
            dispatch_completion(
                run=refreshed,
                agent=agent,
                store=store,
                broadcaster=broadcaster,
                transcript_path=transcript_path,
                settings=settings,
            )
    except Exception:
        logger.exception("cancel dispatch failed for %s", run_id)
    return True
