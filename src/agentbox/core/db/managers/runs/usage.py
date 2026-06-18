"""UsageManager — token usage CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.usage import Usage


class UsageManager(Manager[Usage]):
    """Manager for the ``usage`` table."""

    model = Usage
