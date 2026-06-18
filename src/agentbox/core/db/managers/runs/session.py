"""SessionManager — conversation session CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.session import Session


class SessionManager(Manager[Session]):
    """Manager for the ``sessions`` table."""

    model = Session
