"""API-layer webhook routes — URL resolution, resend, agent-event hooks.

These are *outbound* webhook operations: agentbox telling a caller that
something happened. Inbound webhooks from agents reporting completion
live in ``api/runs/crud.py`` (``/complete`` and ``/post_outcome``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from agentbox.api.deps import get_settings
from agentbox.core.config import Settings
from agentbox.core.execution.dispatch import deliver_webhook, dispatch_completion
from agentbox.core.execution.dispatch.payload import AgentEventPayload, build_completion_payload
from agentbox.core.execution.dispatch.policy import apply_delivery_outcome
from agentbox.core.service import AgentDef, ExecutionService, RunRecord

logger = logging.getLogger(__name__)


def _resolve_webhook_url(agent: AgentDef | None) -> str | None:
    """Resolve the webhook URL from agent config, then global settings."""
    if agent is not None and agent.webhook_url is not None:
        return agent.webhook_url or None
    try:
        settings = get_settings()
    except Exception:
        return None
    return getattr(settings, "completion_webhook_url", None)


def schedule_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: Any | None = None,
    broadcaster: Any | None = None,
    transcript_path: Path | None = None,
) -> None:
    """Schedule webhook delivery, resolving the URL through agent + settings.

    Thin wrapper around :func:`dispatch_completion` that preserves the
    historical callback signature used by ``api/runs/crud.py`` and the
    lifecycle service. The ``store`` parameter is accepted for backward
    compatibility with callers that still pass a ``SessionStore``; it is
    not forwarded to dispatch — an :class:`ExecutionService` is constructed
    internally instead, since the run-lifecycle methods required by dispatch
    were removed from ``SessionStore`` in plan 088.
    """
    settings = get_settings()
    exec_svc = ExecutionService()
    dispatch_completion(
        run=run,
        agent=agent,
        store=exec_svc,
        broadcaster=broadcaster,
        transcript_path=transcript_path,
        settings=settings if isinstance(settings, Settings) else None,
    )


async def resend_webhook(
    agent: AgentDef | None,
    run: RunRecord,
) -> tuple[bool, str | None]:
    """Synchronously re-deliver the webhook for ``run``."""
    url = _resolve_webhook_url(agent)
    if not url:
        return False, "no webhook_url configured"
    exec_svc = ExecutionService()
    payload = build_completion_payload(run, exec_svc)
    delivered = await deliver_webhook(url, payload)
    apply_delivery_outcome(exec_svc, run.id, delivered)
    return delivered, None if delivered else "delivery failed; see server logs"


def schedule_agent_event_webhook(
    *,
    webhook_url: str,
    event: str,
    agent_id: str,
    version: int,
    version_id: int,
    reason: str,
) -> None:
    """Best-effort: schedule an agent event webhook."""
    payload: AgentEventPayload = {
        "event": event,
        "agent_id": agent_id,
        "version": version,
        "version_id": version_id,
        "reason": reason,
        "published_at": datetime.now().isoformat(),
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "no running event loop; cannot deliver agent event webhook for %s v%s",
            agent_id,
            version,
        )
        return
    task = loop.create_task(deliver_webhook(webhook_url, payload))

    def log_outcome(t: asyncio.Task[bool]) -> None:
        if t.cancelled():
            return
        try:
            delivered = t.result()
            level = "info" if delivered else "error"
            msg = f"agent.published webhook {'delivered' if delivered else 'failed'}"
        except Exception:
            delivered = False
            level = "error"
            msg = "agent.published webhook delivery error"
        logger.log(
            getattr(logging, level.upper()),
            "%s for %s v%s",
            msg,
            agent_id,
            version,
        )

    task.add_done_callback(log_outcome)
