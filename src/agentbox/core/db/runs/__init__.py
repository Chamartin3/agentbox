"""Runs domain — core execution records.

One file per table (entity + manager together). The manager is the public
surface; the entity is importable directly for cross-domain FK references.
"""
from __future__ import annotations

from agentbox.core.db.runs.run import Run, RunManager
from agentbox.core.db.runs.session import Session, SessionManager
from agentbox.core.db.runs.usage import Usage, UsageManager
from agentbox.core.db.runs.comment import RunComment, RunCommentManager
from agentbox.core.db.runs.run_prompt import RunPrompt, RunPromptManager
from agentbox.core.db.runs.webhook import WebhookDelivery, WebhookDeliveryManager

__all__ = [
    # entities
    "Run",
    "Session",
    "Usage",
    "RunComment",
    "RunPrompt",
    "WebhookDelivery",
    # managers
    "RunManager",
    "SessionManager",
    "UsageManager",
    "RunCommentManager",
    "RunPromptManager",
    "WebhookDeliveryManager",
]
