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
from pathlib import Path
from typing import Any

import httpx

from agentbox.api.events import LogEvent, RunEvent
from agentbox.core.constants import RunStatus
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
        "validation_status": run.validation_status,
        "schema_validated_via": run.schema_validated_via,
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


def _build_payload(
    run: RunRecord, store: SessionStore
) -> dict[str, Any]:
    usage = store.get_usage(run.id)
    duration_ms: int | None = None
    if run.created_at and run.finished_at:
        try:
            started = datetime.fromisoformat(run.created_at)
            ended = datetime.fromisoformat(run.finished_at)
            duration_ms = int((ended - started).total_seconds() * 1000)
        except (ValueError, TypeError):
            duration_ms = None
    return webhook_payload(run, usage=usage, duration_ms=duration_ms)


def _on_delivery_done(
    task: asyncio.Task[bool], run_id: str, store: SessionStore
) -> None:
    """Done-callback: flip ``ok`` → ``incomplete`` when delivery failed.

    ``error`` and ``incomplete`` runs are left untouched — we only
    downgrade a successful run to signal that the consumer never saw
    the notification.
    """
    if task.cancelled():
        return
    try:
        delivered = task.result()
    except Exception:  # pragma: no cover — deliver_webhook swallows
        delivered = False
    if delivered:
        # If a manual resend through schedule_webhook ever happens for
        # an ``incomplete`` run, promote it back to ``ok``.
        try:
            current = store.get_run(run_id)
            if current is not None and current.status == RunStatus.INCOMPLETE:
                store.set_run_status(run_id, RunStatus.OK)
        except Exception:
            logger.exception("failed promoting run %s back to ok", run_id)
        return
    try:
        current = store.get_run(run_id)
        if current is not None and current.status == RunStatus.OK:
            store.set_run_status(run_id, RunStatus.INCOMPLETE)
    except Exception:
        logger.exception("failed marking run %s incomplete", run_id)


def schedule_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: SessionStore,
    broadcaster: Any | None = None,
    transcript_path: Path | None = None,
) -> None:
    """Best-effort: schedule webhook delivery if a URL is configured.

    Safe to call from a sync code path — it grabs the running loop and
    queues a task. Silently skips when there's no URL or no event loop.
    On delivery failure the run is flipped to ``incomplete`` so an
    operator can resend.
    """
    url = _resolve_webhook_url(agent)
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
        _deliver_with_events(url, payload, run_id, broadcaster, transcript_path)
    )
    task.add_done_callback(lambda t: _on_delivery_done(t, run_id, store))


async def _deliver_with_events(
    url: str,
    payload: dict[str, Any],
    run_id: str,
    broadcaster: Any | None,
    transcript_path: Path | None,
) -> bool:
    """Wrap deliver_webhook with per-attempt event emission."""
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
                _emit(
                    broadcaster,
                    transcript_path,
                    LogEvent(
                        level="info",
                        message=f"webhook delivered (attempt {attempt + 1})",
                        run_id=run_id,
                    ),
                )
                return True
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        _emit(
            broadcaster,
            transcript_path,
            LogEvent(
                level="warn",
                message=f"webhook attempt {attempt + 1} failed: {last_error}",
                run_id=run_id,
            ),
        )
        await asyncio.sleep(delay)
    _emit(
        broadcaster,
        transcript_path,
        LogEvent(
            level="error",
            message=f"webhook delivery failed after {len(_RETRY_DELAYS_S)} attempts: {last_error}",
            run_id=run_id,
        ),
    )
    return False


def _emit(
    broadcaster: Any | None,
    transcript_path: Path | None,
    ev: RunEvent,
) -> None:
    """Publish an event and persist it to the transcript, best-effort."""
    if broadcaster is not None:
        try:
            broadcaster.publish(ev)
        except Exception:
            pass
    if transcript_path is not None:
        try:
            with transcript_path.open("a", encoding="utf-8") as tf:
                tf.write(ev.model_dump_json() + "\n")
        except OSError:
            pass


async def resend_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: SessionStore,
) -> tuple[bool, str | None]:
    """Synchronously re-deliver the webhook for ``run``.

    Returns ``(delivered, reason)``. On success the run's status is
    promoted from ``incomplete`` back to ``ok``; on failure an ``ok``
    run is demoted to ``incomplete``. ``error`` runs keep their status.
    """
    url = _resolve_webhook_url(agent)
    if not url:
        return False, "no webhook_url configured"
    payload = _build_payload(run, store)
    delivered = await deliver_webhook(url, payload)
    current = store.get_run(run.id)
    if current is None:
        return delivered, None
    if delivered and current.status == RunStatus.INCOMPLETE:
        store.set_run_status(run.id, RunStatus.OK)
    elif not delivered and current.status == RunStatus.OK:
        store.set_run_status(run.id, RunStatus.INCOMPLETE)
    return delivered, None if delivered else "delivery failed; see server logs"
