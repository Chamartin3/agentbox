"""Fire-and-forget webhook delivery for terminal run events.

Agents may declare a ``webhook_url`` in their definition. When one of their
runs reaches a terminal state (ok / error), we POST a JSON envelope to
that URL describing the outcome. Delivery is best-effort with a few
retries — agentbox owns the run state, the webhook is just a courtesy
notification so consumers can react without polling.

Spawned as a background task so the request that finalised the run
(usually ``/api/runs/{id}/complete``) can return immediately.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx

from agentbox.core.data import AgentDef, RunRecord, SessionStore

logger = logging.getLogger(__name__)

_RETRY_DELAYS_S = (1.0, 3.0, 9.0)
_HTTP_TIMEOUT_S = 10.0


def webhook_payload(
    run: RunRecord,
    *,
    usage: dict[str, Any] | None,
    duration_ms: int | None,
) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "session_id": run.session_id,
        "status": run.status,
        "output": run.output,
        "error": run.error,
        "started_at": run.created_at,
        "finished_at": run.finished_at,
        "duration_ms": duration_ms,
        "usage": usage,
    }


async def deliver_webhook(url: str, payload: dict[str, Any]) -> bool:
    """POST `payload` to `url`, retrying on transient failure.

    Returns True on the first 2xx, False if all attempts fail. Any
    failure is logged with the run_id so an operator can correlate.
    """
    body = json.dumps(payload, default=str)
    last_error: str = ""
    for attempt, delay in enumerate(_RETRY_DELAYS_S):
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
            if 200 <= resp.status_code < 300:
                return True
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "webhook attempt %d failed for run %s: %s",
            attempt + 1,
            payload.get("run_id"),
            last_error,
        )
        await asyncio.sleep(delay)
    logger.error(
        "webhook delivery failed for run %s after %d attempts: %s",
        payload.get("run_id"),
        len(_RETRY_DELAYS_S),
        last_error,
    )
    return False


def _resolve_webhook_url(agent: AgentDef | None) -> str | None:
    """Per-agent ``webhook_url`` wins; falls back to global setting.

    Empty string on the agent means "explicitly opt out" even when a
    global default is configured.
    """
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


def schedule_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: SessionStore,
) -> None:
    """Best-effort: schedule webhook delivery if a URL is configured.

    Safe to call from a sync code path — it grabs the running loop and
    queues a task. Silently skips when there's no URL or no event loop.
    """
    url = _resolve_webhook_url(agent)
    if not url:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "no running event loop; cannot deliver webhook for run %s", run.id
        )
        return
    usage = store.get_usage(run.id)
    duration_ms: int | None = None
    if run.created_at and run.finished_at:
        try:
            started = datetime.fromisoformat(run.created_at)
            ended = datetime.fromisoformat(run.finished_at)
            duration_ms = int((ended - started).total_seconds() * 1000)
        except (ValueError, TypeError):
            duration_ms = None
    payload = webhook_payload(run, usage=usage, duration_ms=duration_ms)
    task = loop.create_task(deliver_webhook(url, payload))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
