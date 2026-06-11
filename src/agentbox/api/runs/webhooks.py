"""API-layer webhook routes — URL resolution, resend, agent-event hooks."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from agentbox.core.service import AgentDef, RunRecord, SessionStore
from agentbox.core.execution.webhooks import deliver_webhook, schedule_webhook as _schedule_webhook

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL resolution (depends on api settings)
# ---------------------------------------------------------------------------


def _resolve_webhook_url(agent: AgentDef | None) -> str | None:
    if agent is None:
        return None
    if agent.webhook_url is not None:
        return agent.webhook_url or None
    try:
        from agentbox.api.deps import get_settings

        settings = get_settings()
    except Exception:
        return None
    return getattr(settings, "completion_webhook_url", None)


# ---------------------------------------------------------------------------
# Public API — thin wrappers around core logic
# ---------------------------------------------------------------------------


def schedule_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: SessionStore,
    broadcaster: Any | None = None,
    transcript_path: Path | None = None,
) -> None:
    """Schedule webhook delivery, resolving the URL through agent + settings."""
    fallback = _resolve_webhook_url(agent)
    return _schedule_webhook(
        agent,
        run,
        store,
        broadcaster,
        transcript_path,
        fallback_webhook_url=fallback,
    )


async def resend_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: SessionStore,
) -> tuple[bool, str | None]:
    """Synchronously re-deliver the webhook for ``run``."""
    url = _resolve_webhook_url(agent)
    if not url:
        return False, "no webhook_url configured"
    from agentbox.core.execution.webhooks import (
        _apply_delivery_outcome,
        _build_payload,
    )

    payload = _build_payload(run, store)
    delivered = await deliver_webhook(url, payload)
    _apply_delivery_outcome(store, run.id, delivered)
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
    from datetime import datetime

    payload = {
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
