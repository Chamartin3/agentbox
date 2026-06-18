"""WebhookDeliveryManager — webhook delivery log CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.webhook import WebhookDelivery


class WebhookDeliveryManager(Manager[WebhookDelivery]):
    """Manager for the ``webhook_deliveries`` table."""

    model = WebhookDelivery
