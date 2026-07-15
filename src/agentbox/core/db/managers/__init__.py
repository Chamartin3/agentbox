"""Managers catalog — re-exports every Manager.

Callers import managers from here or from the ``core.db`` façade:
    from agentbox.core.db.managers.runs import RunManager
    from agentbox.core.db.managers import RunManager, WorkspaceManager
"""
from __future__ import annotations

# Runs domain
from agentbox.core.db.managers.runs import (
    RunCommentManager,
    RunManager,
    RunPromptManager,
    SessionManager,
    UsageManager,
    WebhookDeliveryManager,
)

__all__ = [
    # runs
    "RunCommentManager",
    "RunManager",
    "RunPromptManager",
    "SessionManager",
    "UsageManager",
    "WebhookDeliveryManager",
]
