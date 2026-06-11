"""Retry policy, status management, and delivery-outcome handlers."""

from __future__ import annotations

import asyncio
import logging

from agentbox.core.constants import RunStatus
from agentbox.core.data import RunStore

logger = logging.getLogger(__name__)

_RETRY_DELAYS_S = (1.0, 3.0, 9.0)
_HTTP_TIMEOUT_S = 10.0


def _apply_delivery_outcome(store: RunStore, run_id: str, delivered: bool) -> None:
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


def _on_delivery_done(
    task: asyncio.Task[bool], run_id: str, store: RunStore
) -> None:
    if task.cancelled():
        return
    try:
        delivered = task.result()
    except Exception:
        delivered = False
    _apply_delivery_outcome(store, run_id, delivered)


__all__ = ["_RETRY_DELAYS_S", "_HTTP_TIMEOUT_S", "_on_delivery_done"]
