"""Webhook delivery engine — no HTTP/FastAPI dependency.

Pure core logic: payload construction, HTTP delivery with retries,
event persistence, and run-status management. The API layer handles
URL resolution and routes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from agentbox.core.constants import RunStatus
from agentbox.core.data import AgentDef, LogEvent, RunEvent, RunRecord, SessionStore
from agentbox.core.execution.validate import extract_json

logger = logging.getLogger(__name__)

_RETRY_DELAYS_S = (1.0, 3.0, 9.0)
_HTTP_TIMEOUT_S = 10.0


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _parsed_output(run: RunRecord) -> Any:
    return run.output or ""


def _parsed_output_structured(run: RunRecord) -> dict[str, Any] | list | None:
    raw = run.output
    if not isinstance(raw, str) or not raw.strip():
        return None
    if run.validation_status != "ok":
        return None
    try:
        return json.loads(extract_json(raw))
    except (ValueError, TypeError):
        return None


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
        "output": _parsed_output(run),
        "output_structured": _parsed_output_structured(run),
        "error": run.error,
        "started_at": run.created_at,
        "finished_at": run.finished_at,
        "duration_ms": duration_ms,
        "usage": usage,
        "validation_status": run.validation_status,
        "schema_validated_via": run.schema_validated_via,
    }


# ---------------------------------------------------------------------------
# HTTP delivery
# ---------------------------------------------------------------------------


async def deliver_webhook(url: str, payload: dict[str, Any]) -> bool:
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


# ---------------------------------------------------------------------------
# Status management
# ---------------------------------------------------------------------------


def _apply_delivery_outcome(store: SessionStore, run_id: str, delivered: bool) -> None:
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
    task: asyncio.Task[bool], run_id: str, store: SessionStore
) -> None:
    if task.cancelled():
        return
    try:
        delivered = task.result()
    except Exception:
        delivered = False
    _apply_delivery_outcome(store, run_id, delivered)


# ---------------------------------------------------------------------------
# Event + delivery recording
# ---------------------------------------------------------------------------


def _response_signals_failure(body: str) -> bool:
    if not body:
        return False
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return False
    if not isinstance(parsed, dict):
        return False
    if parsed.get("ok") is False:
        return True
    status_field = parsed.get("status")
    return bool(
        isinstance(status_field, str)
        and status_field.lower() in {"error", "failed", "fail"}
    )


def _record_delivery(
    store: SessionStore | None,
    run_id: str,
    attempt: int,
    url: str,
    payload: dict[str, Any] | None,
    status: int | None = None,
    body: str | None = None,
    latency: int | None = None,
    error: str | None = None,
) -> None:
    if store is None:
        return
    try:
        store.record_webhook_delivery(
            run_id=run_id,
            attempt=attempt,
            url=url,
            payload=payload,
            response_status=status,
            response_body=body,
            latency_ms=latency,
            error=error,
        )
    except Exception:
        logger.exception("failed to record webhook delivery for run %s", run_id)


def _emit(
    broadcaster: Any | None,
    transcript_path: Path | None,
    ev: RunEvent,
) -> None:
    if broadcaster is not None:
        with contextlib.suppress(Exception):
            broadcaster.publish(ev)
    if transcript_path is not None:
        try:
            with transcript_path.open("a", encoding="utf-8") as tf:
                tf.write(ev.model_dump_json() + "\n")
        except OSError:
            pass


async def _deliver_with_events(
    url: str,
    payload: dict[str, Any],
    run_id: str,
    broadcaster: Any | None,
    transcript_path: Path | None,
    store: SessionStore | None = None,
) -> bool:
    body = json.dumps(payload, default=str)
    last_error: str = ""
    datetime.now()
    for attempt, delay in enumerate(_RETRY_DELAYS_S):
        attempt_start = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
            latency = int((datetime.now() - attempt_start).total_seconds() * 1000)
            body_signals_failure = _response_signals_failure(resp.text)
            if 200 <= resp.status_code < 300 and not body_signals_failure:
                _record_delivery(
                    store,
                    run_id,
                    attempt + 1,
                    url,
                    payload,
                    status=resp.status_code,
                    body=resp.text[:500],
                    latency=latency,
                )
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
            if body_signals_failure:
                last_error = (
                    f"HTTP {resp.status_code} but body signals failure: "
                    f"{resp.text[:200]}"
                )
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            _record_delivery(
                store,
                run_id,
                attempt + 1,
                url,
                payload,
                status=resp.status_code,
                body=resp.text[:500],
                latency=latency,
                error=last_error,
            )
        except httpx.HTTPError as exc:
            latency = int((datetime.now() - attempt_start).total_seconds() * 1000)
            last_error = f"{type(exc).__name__}: {exc}"
            _record_delivery(
                store,
                run_id,
                attempt + 1,
                url,
                payload,
                latency=latency,
                error=last_error,
            )
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


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def _build_payload(run: RunRecord, store: SessionStore) -> dict[str, Any]:
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


def schedule_webhook(
    agent: AgentDef | None,
    run: RunRecord,
    store: SessionStore,
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


__all__ = [
    "deliver_webhook",
    "schedule_webhook",
    "WebhookDispatcher",
    "webhook_payload",
]


# ---------------------------------------------------------------------------
# Dispatcher (used by the finalizer)
# ---------------------------------------------------------------------------


class WebhookDispatcher:
    """Fire completion webhooks for terminal runs."""

    def __init__(self, store: SessionStore) -> None:
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
