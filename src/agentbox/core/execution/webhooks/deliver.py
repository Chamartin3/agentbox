"""HTTP delivery with retries, event persistence, and response analysis."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from agentbox.core.data import LogEvent, RunEvent, RunStore
from agentbox.core.execution.webhooks.policy import _HTTP_TIMEOUT_S, _RETRY_DELAYS_S

logger = logging.getLogger(__name__)


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
    store: RunStore | None,
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


async def _deliver_with_events(
    url: str,
    payload: dict[str, Any],
    run_id: str,
    broadcaster: Any | None,
    transcript_path: Path | None,
    store: RunStore | None = None,
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


__all__ = ["_deliver_with_events", "deliver_webhook"]
