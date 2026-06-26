"""Feedback service — run comment CRUD.

Analytics (aggregate_usage, activity_summary, distinct_executors,
enrich_recent_runs) moved to EvaluationService (plan 093).
Public callers (api/, cli/, mcp/) should use EvaluationService for
analytics and import only add_comment / list_comments from here.
"""

from __future__ import annotations

from agentbox.core.service.execution.feedback.comments import (
    add_comment,
    list_comments,
)

__all__ = [
    "add_comment",
    "list_comments",
]
