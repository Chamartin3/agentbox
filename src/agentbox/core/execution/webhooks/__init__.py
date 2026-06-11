"""Webhook delivery engine — no HTTP/FastAPI dependency.

All logic lives under ``agentbox.core.execution.webhooks.*``.
This module is the public facade.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from agentbox.core.data import AgentDef, LogEvent, RunRecord, RunStore

from agentbox.core.execution.webhooks.deliver import (
    _deliver_with_events,
    _emit,
    deliver_webhook,
)
from agentbox.core.execution.webhooks.payload import (
    _build_payload,
    _parsed_output,
    _parsed_output_structured,
    webhook_payload,
)
from agentbox.core.execution.webhooks.policy import _on_delivery_done

logger = logging.getLogger(__name__)


def schedule_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: RunStore,
    broadcaster: Any | None = None,
    transcript_path: Path | None = None,
    *,
    fallback_webhook_url: str | None = None,
) -> None:
    """Best-effort: schedule webhook delivery if a URL is configured."""
    url = None
    if agent is not None and agent.webhook_url is not None:
        url = agent.webhook_url or None
    if not url:
        url = fallback_webhook_url
    if not url:
        return
    _emit(
        broadcaster,
        transcript_path,
        LogEvent(level="info", message=f"webhook scheduled → {url}", run_id=run.id),
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "no running event loop; cannot deliver webhook for run %s", run.id
        )
        return
    payload = _build_payload(run, store)
    run_id = run.id
    task = loop.create_task(
        _deliver_with_events(
            url, payload, run_id, broadcaster, transcript_path, store=store
        )
    )
    task.add_done_callback(lambda t: _on_delivery_done(t, run_id, store))


class WebhookDispatcher:
    """Fire completion webhooks for terminal runs."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def deliver(
        self,
        run_id: str,
        agent: AgentDef | None,
        broadcaster: Any | None,
        transcript_path: Path | None,
    ) -> None:
        try:
            refreshed = self._store.get_run(run_id)
            if refreshed is None:
                return
            schedule_webhook(
                agent,
                refreshed,
                self._store,
                broadcaster,
                transcript_path,
            )
        except Exception:
            logger.exception("webhook scheduling failed for %s", run_id)

    def deliver_for_cancel(
        self,
        run_id: str,
        broadcaster: Any | None,
    ) -> None:
        try:
            refreshed = self._store.get_run(run_id)
            if refreshed is None:
                return
            agent: AgentDef | None = None
            try:
                agent = self._store.get_agent_def(refreshed.agent_id)
            except Exception:
                logger.exception(
                    "cancel webhook: failed to resolve agent for run %s", run_id
                )
            transcript_path = (
                Path(refreshed.transcript_path)
                if refreshed.transcript_path
                else None
            )
            schedule_webhook(
                agent,
                refreshed,
                self._store,
                broadcaster,
                transcript_path,
            )
        except Exception:
            logger.exception("cancel webhook scheduling failed for %s", run_id)


__all__ = [
    "WebhookDispatcher",
    "_parsed_output",
    "_parsed_output_structured",
    "deliver_webhook",
    "schedule_webhook",
    "webhook_payload",
]
