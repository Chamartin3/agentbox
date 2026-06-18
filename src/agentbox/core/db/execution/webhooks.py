"""Webhook delivery CRUD mixin."""

from __future__ import annotations

import warnings

import json as _json

from sqlalchemy.engine import Engine

from agentbox.core.db.schema import webhook_deliveries
from agentbox.core.db.utils import now_iso


class WebhooksMixin:
    """Webhook delivery CRUD requiring ``self.engine: Engine``."""

    engine: Engine

    def record_webhook_delivery(
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
        warnings.warn(
            "WebhooksMixin.record_webhook_delivery is deprecated; use db.webhook_deliveries manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.begin() as conn:
            conn.execute(
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

    def list_webhook_deliveries(self, run_id: str) -> list[dict]:
        warnings.warn(
            "WebhooksMixin.list_webhook_deliveries is deprecated; use db.webhook_deliveries manager instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.engine.connect() as conn:
            rows = conn.execute(
                webhook_deliveries.select()
                .where(webhook_deliveries.c.run_id == run_id)
                .order_by(webhook_deliveries.c.id)
            )
            return [dict(r._mapping) for r in rows]
