"""WebhookDeliveryManager — webhook delivery log CRUD."""
from __future__ import annotations

import json as _json

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.webhook import WebhookDelivery
from agentbox.core.db.schema import webhook_deliveries
from agentbox.core.db.utils import now_iso


class WebhookDeliveryManager(Manager[WebhookDelivery]):
    """Manager for the ``webhook_deliveries`` table."""

    model = WebhookDelivery

    def record(
        self,
        run_id: str,
        attempt: int,
        url: str,
        payload: dict | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        """Insert a webhook delivery attempt log row."""
        self._query(
            webhook_deliveries.insert().values(
                run_id=run_id,
                attempt=attempt,
                url=url,
                payload_json=_json.dumps(payload) if payload else None,
                response_status=response_status,
                response_body=response_body,
                latency_ms=latency_ms,
                error=error,
                ts=now_iso(),
            )
        )

    def list_for_run(self, run_id: str) -> list[dict]:
        """List all webhook delivery attempts for a run ordered by id."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                webhook_deliveries.select()
                .where(webhook_deliveries.c.run_id == run_id)
                .order_by(webhook_deliveries.c.id)
            )
            return [dict(r._mapping) for r in rows]
