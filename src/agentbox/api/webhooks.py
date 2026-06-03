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
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from agentbox.core.data import LogEvent, RunEvent
from agentbox.core.constants import RunStatus
from agentbox.core.data import AgentDef, RunRecord, SessionStore
from agentbox.core.execution.validate import extract_json

logger = logging.getLogger(__name__)

_RETRY_DELAYS_S = (1.0, 3.0, 9.0)
_HTTP_TIMEOUT_S = 10.0


def _parsed_output(run: RunRecord) -> Any:
    """Return ``run.output`` as a raw string, always.

    The webhook ``output`` field is unconditionally the verbatim string
    stored on the run — regardless of backend or validation status.
    This keeps the webhook contract stable: receivers can always treat
    ``output`` as a string without worrying about backend-specific
    pre-parsing.

    For the structured (dict/list) form when a schema was validated,
    use :func:`_parsed_output_structured`.
    """
    return run.output or ""


def _parsed_output_structured(run: RunRecord) -> dict[str, Any] | list | None:
    """Return ``run.output`` as a structured dict/list when applicable.

    Only returns a non-null value when the run was schema-validated
    (``validation_status == "ok"``) and the output is parseable JSON.
    For raw-text or non-validated runs returns ``None``.
    """
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


def _on_delivery_done(
    task: asyncio.Task[bool], run_id: str, store: SessionStore
) -> None:
    """Done-callback: flip ``ok`` → ``failed`` when webhook delivery fails.

    ``error``, ``failed``, ``stopped``, ``timeout`` runs are left
    untouched — we only downgrade a successful run to signal that the
    consumer never saw the notification. Failure to submit the response
    is an expected, recoverable outcome (network blip, consumer down),
    so it lives in the ``failed`` bucket alongside other connection
    failures rather than the unexpected-crash ``error`` bucket.
    """
    if task.cancelled():
        return
    try:
        delivered = task.result()
    except Exception:  # pragma: no cover — deliver_webhook swallows
        delivered = False
    _apply_delivery_outcome(store, run_id, delivered)


def _apply_delivery_outcome(store: SessionStore, run_id: str, delivered: bool) -> None:
    """Update a run's status based on webhook delivery outcome.

    Shared by the background done-callback and the synchronous
    ``resend_webhook`` path so both follow the same rules. Promotes
    ``failed`` rows back to ``ok`` on a successful resend *only* when
    ``failed`` was caused by a prior delivery failure (``error`` empty).
    Real agent-level failures — validation, rate-limit, auth — also
    classify as ``failed`` and set ``error``; those must not be flipped
    to ``ok`` just because the courtesy webhook landed. ``incomplete``
    rows are orphan-reaped: the agent never finished, so a webhook
    delivery cannot make them ``ok``.
    """
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
    On delivery failure the run is flipped to ``failed`` so an
    operator can resend; the agent itself ran fine, but the pipeline
    didn't complete end-to-end.
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
        _deliver_with_events(
            url, payload, run_id, broadcaster, transcript_path, store=store
        )
    )
    task.add_done_callback(lambda t: _on_delivery_done(t, run_id, store))


async def _deliver_with_events(
    url: str,
    payload: dict[str, Any],
    run_id: str,
    broadcaster: Any | None,
    transcript_path: Path | None,
    store: SessionStore | None = None,
) -> bool:
    """Wrap deliver_webhook with per-attempt event emission and persistence."""
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


def _response_signals_failure(body: str) -> bool:
    """Detect consumer-side failure in a 2xx webhook response.

    Some receivers (Django views, mostly) historically returned 200 OK with
    ``{"ok": false}`` even when the post-processor blew up. That swallows the
    failure: agentbox marked the run delivered, but no data was persisted.
    Inspect the JSON body when present and treat ``ok: false`` / ``status:
    error``/``failed`` as a delivery failure so the run gets retried and then
    flipped to ``failed`` if it never recovers.
    """
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
    """Publish an event and persist it to the transcript, best-effort."""
    if broadcaster is not None:
        with contextlib.suppress(Exception):
            broadcaster.publish(ev)
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
    promoted from ``failed`` (or legacy ``incomplete``) back to ``ok``;
    on failure an ``ok`` run is demoted to ``failed``. Other terminal
    statuses (``error``, ``stopped``, ``timeout``) keep their status.
    """
    url = _resolve_webhook_url(agent)
    if not url:
        return False, "no webhook_url configured"
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
    """Best-effort: schedule an agent event webhook.

    Spawns a background task to POST a JSON envelope to the webhook URL.
    Silently skips when there's no event loop (safe for sync code paths).

    Args:
        webhook_url: URL to POST the event to.
        event: Event type (e.g. "agent.published").
        agent_id: Agent identifier.
        version: Version number.
        version_id: Version ID in the DB.
        reason: Reason/changelog for the event.
    """
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
        except Exception:  # pragma: no cover
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
