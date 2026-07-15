"""WebhookDelivery model + manager — webhook callback delivery log.

Maps to the ``webhook_deliveries`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional
import json as _json
from typing import cast

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity
from agentbox.core.data.rows import WebhookDeliveryRow
from agentbox.core.db.base.manager import Manager
from agentbox.core.data._util import now_iso


class WebhookDelivery(Entity, table=True):
    """A single webhook delivery attempt for a run."""

    __tablename__ = tablename("webhook_deliveries")

    id: int = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", nullable=False)
    attempt: int = Field(nullable=False)
    url: str = Field(nullable=False)
    payload_json: Optional[str] = Field(default=None)
    response_status: Optional[int] = Field(default=None)
    response_body: Optional[str] = Field(default=None)
    latency_ms: Optional[int] = Field(default=None)
    error: Optional[str] = Field(default=None)
    ts: str = Field(nullable=False)

    __table_args__ = tableargs(
        Index("idx_webhook_deliveries_run", "run_id"),
    )


webhook_deliveries = WebhookDelivery.__table__  # table sourced from the SQLModel entity


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

    def list_for_run(self, run_id: str) -> list[WebhookDeliveryRow]:
        """List all webhook delivery attempts for a run ordered by id."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                webhook_deliveries.select()
                .where(webhook_deliveries.c.run_id == run_id)
                .order_by(webhook_deliveries.c.id)
            )
            return [cast(WebhookDeliveryRow, dict(r._mapping)) for r in rows]
