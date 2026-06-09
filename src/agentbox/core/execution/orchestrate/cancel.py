"""Run cancellation logic extracted from RunExecutor."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from agentbox.core.constants import RunStatus
from agentbox.core.data import DoneEvent, LogEvent

if TYPE_CHECKING:
    from agentbox.core.execution.orchestrate.broadcaster import RunBroadcaster
    from agentbox.core.execution.webhooks import WebhookDispatcher
    from agentbox.core.data import RunStore

logger = logging.getLogger(__name__)


def cancel_run(
    *,
    run_id: str,
    store: RunStore,
    broadcasters: dict[str, RunBroadcaster],
    run_tasks: dict[str, asyncio.Task[None]],
    webhooks: WebhookDispatcher,
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
                LogEvent(run_id=run_id, level="warn", message=error_msg)
            )
            broadcaster.publish(
                DoneEvent(
                    run_id=run_id,
                    ok=False,
                    error=error_msg,
                    status=RunStatus.INCOMPLETE.value,
                )
            )

    task.cancel()
    webhooks.deliver_for_cancel(run_id, broadcaster)
    return True
