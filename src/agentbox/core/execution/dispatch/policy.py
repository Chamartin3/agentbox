"""Dispatch policy and delivery-outcome handling.

A ``DispatchPolicy`` configures retry/backoff/timeout behavior for one
dispatch attempt. The outcome handlers mirror the historical webhook
semantics: a failed delivery can flip a successful run back to failed
so the operator notices and can resend.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from agentbox.core.constants import RunStatus
from agentbox.core.db import RunStore

from agentbox.core.execution.dispatch.channels.types import DeliveryResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DispatchPolicy:
    """Channel-agnostic retry / backoff / timeout configuration."""

    retry_delays_s: tuple[float, ...] = (1.0, 3.0, 9.0)
    request_timeout_s: float = 10.0


def apply_delivery_outcome(store: RunStore, run_id: str, delivered: bool) -> None:
    """Update the run row based on whether the dispatch succeeded.

    Matches the historical webhook behavior: a delivery failure on an
    otherwise-ok run flips it to failed, and a successful delivery on a
    failed-but-clean run flips it back to ok.
    """
    try:
        current = store.get_run(run_id)
    except Exception:
        logger.exception("failed reading run %s for delivery outcome", run_id)
        return
    if current is None:
        return
    if delivered:
        if current.status == RunStatus.FAILED and not current.error:
            try:
                store.set_run_status(run_id, RunStatus.OK)
            except Exception:
                logger.exception("failed promoting run %s back to ok", run_id)
        return
    if current.status == RunStatus.OK:
        try:
            store.set_run_status(run_id, RunStatus.FAILED)
        except Exception:
            logger.exception("failed marking run %s as failed", run_id)


def on_delivery_done(
    task: asyncio.Task[DeliveryResult], run_id: str, store: RunStore
) -> None:
    """Callback for dispatch task completion."""
    if task.cancelled():
        return
    try:
        result = task.result()
        delivered = result.ok
    except Exception:
        delivered = False
    apply_delivery_outcome(store, run_id, delivered)


__all__ = [
    "DispatchPolicy",
    "apply_delivery_outcome",
    "on_delivery_done",
]
