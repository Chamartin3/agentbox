"""Completion webhook delivery.

Thin wrapper over :func:`agentbox.api.webhooks.schedule_webhook` that
isolates the executor from the (re)fetching dance: the run row is
re-read from the store so the delivered payload reflects the persisted
terminal state — not the in-flight values the executor was carrying.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agentbox.api.webhooks import schedule_webhook
from agentbox.core.data import AgentDef, SessionStore

from agentbox.core.run.execute.broadcaster import RunBroadcaster

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Fire completion webhooks for terminal runs."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def deliver(
        self,
        run_id: str,
        agent: AgentDef | None,
        broadcaster: RunBroadcaster | None,
        transcript_path: Path | None,
    ) -> None:
        """Best-effort webhook delivery for ``run_id``.

        The terminal run row is re-read from the store so the payload
        matches what's persisted. Errors are swallowed: a failed
        webhook never fails a run.
        """
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
        broadcaster: RunBroadcaster | None,
    ) -> None:
        """Cancel-path webhook delivery — resolves agent on demand.

        Mirrors :meth:`deliver` but resolves the agent from the store
        because the cancel caller may not have it in hand. The normal
        completion path does have ``agent`` already and uses
        :meth:`deliver` directly.
        """
        try:
            refreshed = self._store.get_run(run_id)
            if refreshed is None:
                return
            agent: AgentDef | None = None
            try:
                from agentbox.core.service.agents import resolve_agent

                agent = resolve_agent(refreshed.agent_id, store=self._store)
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


__all__ = ["WebhookDispatcher"]
