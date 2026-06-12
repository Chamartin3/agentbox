"""Dispatch facade — pluggable completion notifications.

"Webhook" is one transport for the same conceptual operation:
*"the run is done — go tell something"*. ``dispatch_completion`` is the
single entry point used by the finalizer; channels are discovered from
the ``agentbox.dispatch_channels`` entry-point group.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, cast

from agentbox.config import Settings
from agentbox.core.data import AgentDef, RunRecord, RunStore

from agentbox.core.execution.dispatch.channels.webhook import WebhookChannel
from agentbox.core.execution.dispatch.payload import CompletionPayload, build_completion_payload
from agentbox.core.execution.dispatch.policy import DispatchPolicy, on_delivery_done
from agentbox.core.execution.dispatch.registry import get_channel

logger = logging.getLogger(__name__)


def resolve_channels(
    run: RunRecord,
    agent: AgentDef | None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Resolve the list of dispatch channel specs for a completed run.

    Today this preserves the single-``webhook_url`` schema: the agent's
    ``webhook_url`` wins, then the global ``completion_webhook_url``
    setting. When a second channel is added, this becomes a list of
    ``{"name": ..., "config": ...}`` rows from agent/workspace/run config.
    """
    url: str | None = None
    if agent is not None and agent.webhook_url is not None:
        url = agent.webhook_url or None
    if not url and settings is not None:
        url = getattr(settings, "completion_webhook_url", None) or None
    if not url:
        return []
    return [{"name": "webhook", "config": {"url": url}}]


def dispatch_completion(
    run: RunRecord,
    agent: AgentDef | None,
    store: RunStore,
    broadcaster: Any | None = None,
    transcript_path: Path | None = None,
    settings: Settings | None = None,
) -> None:
    """Schedule all configured dispatch channels for a completed run.

    Best-effort: failures are logged and swallowed. Each channel runs in
    its own background task so slow transports cannot block finalization.
    """
    channels = resolve_channels(run, agent, settings)
    if not channels:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "no running event loop; cannot dispatch completion for run %s", run.id
        )
        return

    payload = build_completion_payload(run, store)
    for spec in channels:
        name = spec.get("name")
        config = spec.get("config", {})
        if not name:
            continue
        try:
            channel_cls = get_channel(name)
        except KeyError:
            logger.error("no dispatch channel registered for name=%r", name)
            continue
        channel = channel_cls()
        task = loop.create_task(
            channel.deliver(
                payload,
                config,
                DispatchPolicy(),
                run_id=run.id,
                broadcaster=broadcaster,
                transcript_path=transcript_path,
                store=store,
            )
        )
        task.add_done_callback(lambda t, rid=run.id: on_delivery_done(t, rid, store))


async def deliver_webhook(url: str, payload: dict[str, Any]) -> bool:
    """Backward-compatible helper: deliver one payload to one URL.

    Used by agent-event webhooks and the resend endpoint, which are not
    full run-completion dispatches. The payload is only JSON-serialized,
    so casting to ``CompletionPayload`` is safe at runtime.
    """
    channel = WebhookChannel()
    result = await channel.deliver(
        cast(CompletionPayload, payload),
        {"url": url},
        DispatchPolicy(),
        run_id=payload.get("run_id", ""),
    )
    return result.ok


__all__ = [
    "dispatch_completion",
    "resolve_channels",
    "deliver_webhook",
]
