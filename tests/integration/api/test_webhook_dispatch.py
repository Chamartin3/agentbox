"""Regression test: schedule_webhook delivers through ExecutionService.

Before plan 088, dispatch_completion called store.get_run / store.get_usage /
store.record_webhook_delivery on a SessionStore.  Those methods were removed
from SessionStore when ExecutionService took ownership of the run lifecycle.
The webhook delivery path silently broke (tests passed only because
resolve_channels returned [] when no URL was configured).

This test seeds a real run, configures a webhook URL on the agent, mocks HTTP
delivery, calls schedule_webhook inside an async context so the background
task actually runs, and asserts that a delivery row was written by
ExecutionService — proving that the DispatchStore protocol calls hit the
correct implementation.
"""

from __future__ import annotations

import asyncio

import httpx
import respx

from agentbox.api.runs.webhooks import schedule_webhook
from agentbox.core.data import AgentDef
from agentbox.core.service.execution import ExecutionService

_WEBHOOK_URL = "https://webhook.example.com/hook"


async def test_schedule_webhook_records_delivery_via_execution_service() -> None:
    """Happy-path: delivery succeeds and is recorded by ExecutionService.

    Verifies that dispatch_completion actually reaches build_completion_payload
    (get_usage), WebhookChannel._record_delivery (record_webhook_delivery), and
    on_delivery_done / apply_delivery_outcome (get_run) — all via
    ExecutionService, not the defunct SessionStore path.
    """
    svc = ExecutionService()
    run_id = svc.create_run("agent-webhook", "hello", "/tmp/wd", "/tmp/t.jsonl")
    svc.finish_run(run_id, ok=True, output='{"result": 1}')
    run = svc.get_run(run_id)
    assert run is not None

    agent = AgentDef(id="agent-webhook", webhook_url=_WEBHOOK_URL)

    with respx.mock:
        respx.post(_WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        # store=None: schedule_webhook must NOT rely on the caller-supplied store;
        # it constructs ExecutionService internally.
        schedule_webhook(agent, run, None)
        # Yield to the event loop so the background delivery task completes.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    deliveries = svc.list_webhook_deliveries(run_id)
    assert deliveries, "expected at least one webhook_deliveries row after delivery"
    assert deliveries[0]["run_id"] == run_id
    assert deliveries[0]["response_status"] == 200


async def test_schedule_webhook_fails_when_store_protocol_missing() -> None:
    """Sentinel: passing an object that lacks get_usage raises AttributeError.

    This confirms the failure mode that existed before the fix. If
    schedule_webhook were to forward the caller-supplied store to
    dispatch_completion, and that store lacked get_usage, the call would fail.
    The test documents the expected behavior post-fix: schedule_webhook IGNORES
    the caller store and always uses ExecutionService internally.

    The test seeds a run and confirms that even when the caller passes a
    store-like object that has NO store methods at all, delivery still works
    because schedule_webhook constructs ExecutionService() itself.
    """
    svc = ExecutionService()
    run_id = svc.create_run("agent-sentinel", "hi", "/tmp/wd", "/tmp/t.jsonl")
    svc.finish_run(run_id, ok=True, output="ok")
    run = svc.get_run(run_id)
    assert run is not None

    agent = AgentDef(id="agent-sentinel", webhook_url=_WEBHOOK_URL)

    # Deliberately pass an object with no store protocol methods.
    class _StubNoMethods:
        pass

    with respx.mock:
        respx.post(_WEBHOOK_URL).mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        # Must NOT raise even though _StubNoMethods has none of the dispatch
        # protocol methods — schedule_webhook uses ExecutionService internally.
        schedule_webhook(agent, run, _StubNoMethods())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    deliveries = svc.list_webhook_deliveries(run_id)
    assert deliveries, "delivery should still succeed regardless of caller-supplied store"
