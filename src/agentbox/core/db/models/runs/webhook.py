"""WebhookDelivery model — webhook callback delivery log.

Maps to the ``webhook_deliveries`` table.
"""
from __future__ import annotations

from agentbox.core.db.base.tablename import tablename, tableargs
from typing import Optional

from sqlmodel import Field, Index

from agentbox.core.db.base.model import Entity


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
