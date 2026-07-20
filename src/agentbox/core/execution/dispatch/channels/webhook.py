"""HTTP webhook dispatch channel."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from agentbox.core.data.constants import LogLevel
from agentbox.core.data.payload_types import WebhookChannelConfig
from agentbox.core.data.events import LogEvent, RunEvent
from agentbox.core.execution.dispatch.channels.base import DeliveryResult, DispatchChannel
from agentbox.core.execution.dispatch.payload import AgentEventPayload, CompletionPayload
from agentbox.core.execution.dispatch.policy import DispatchPolicy, DispatchStore

logger = logging.getLogger(__name__)


def _response_signals_failure(body: str) -> bool:
    """Detect a JSON body that reports failure despite a 2xx status."""
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
    store: DispatchStore | None,
    run_id: str,
    attempt: int,
    url: str,
    payload: CompletionPayload | AgentEventPayload | None,
    status: int | None = None,
    body: str | None = None,
    latency: int | None = None,
    error: str | None = None,
) -> None:
    """Persist one delivery attempt to the historical webhook log table."""
    if store is None:
        return
    try:
        store.record_webhook_delivery(
            run_id=run_id,
            attempt=attempt,
            url=url,
            payload=dict(payload) if payload is not None else None,
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
    """Publish an event to the broadcaster and append it to the transcript."""
    if broadcaster is not None:
        with contextlib.suppress(Exception):
            broadcaster.publish(ev)
    if transcript_path is not None:
        try:
            with transcript_path.open("a", encoding="utf-8") as tf:
                tf.write(ev.model_dump_json() + "\n")
        except OSError:
            pass


def _payload_to_json(payload: CompletionPayload | AgentEventPayload) -> str:
    return json.dumps(payload, default=str)


class WebhookChannel(DispatchChannel):
    """Deliver completion payloads via HTTP POST with retries."""

    name = "webhook"

    async def deliver(
        self,
        payload: CompletionPayload | AgentEventPayload,
        config: WebhookChannelConfig,
        policy: DispatchPolicy,
        *,
        run_id: str,
        broadcaster: Any | None = None,
        transcript_path: Path | None = None,
        store: DispatchStore | None = None,
    ) -> DeliveryResult:
        url = str(config.get("url", ""))
        if not url:
            return DeliveryResult(ok=False, attempts=0, last_error="no webhook URL")

        body = _payload_to_json(payload)
        last_error = ""
        attempts = 0

        _emit(
            broadcaster,
            transcript_path,
            LogEvent(
                level=LogLevel.INFO,
                message=f"webhook scheduled → {url}",
                run_id=run_id,
            ),
        )

        for attempt, delay in enumerate(policy.retry_delays_s):
            attempts = attempt + 1
            attempt_start = datetime.now()
            try:
                async with httpx.AsyncClient(
                    timeout=policy.request_timeout_s
                ) as client:
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
                        attempts,
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
                            level=LogLevel.INFO,
                            message=f"webhook delivered (attempt {attempts})",
                            run_id=run_id,
                        ),
                    )
                    return DeliveryResult(
                        ok=True,
                        attempts=attempts,
                        response_status=resp.status_code,
                    )
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
                    attempts,
                    url,
                    payload,
                    status=resp.status_code,
                    body=resp.text[:500],
                    latency=latency,
                    error=last_error,
                )
            except httpx.HTTPError as exc:
                latency = int(
                    (datetime.now() - attempt_start).total_seconds() * 1000
                )
                last_error = f"{type(exc).__name__}: {exc}"
                _record_delivery(
                    store,
                    run_id,
                    attempts,
                    url,
                    payload,
                    latency=latency,
                    error=last_error,
                )
            _emit(
                broadcaster,
                transcript_path,
                LogEvent(
                    level=LogLevel.WARN,
                    message=f"webhook attempt {attempts} failed: {last_error}",
                    run_id=run_id,
                ),
            )
            await asyncio.sleep(delay)

        _emit(
            broadcaster,
            transcript_path,
            LogEvent(
                level=LogLevel.ERROR,
                message=(
                    f"webhook delivery failed after {attempts} attempts: "
                    f"{last_error}"
                ),
                run_id=run_id,
            ),
        )
        return DeliveryResult(ok=False, attempts=attempts, last_error=last_error)


__all__ = ["WebhookChannel"]
