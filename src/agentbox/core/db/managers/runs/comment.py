"""RunCommentManager — run comment CRUD."""
from __future__ import annotations

from agentbox.core.db.base.manager import Manager
from agentbox.core.db.models.runs.comment import RunComment


class RunCommentManager(Manager[RunComment]):
    """Manager for the ``run_comments`` table."""

    model = RunComment
