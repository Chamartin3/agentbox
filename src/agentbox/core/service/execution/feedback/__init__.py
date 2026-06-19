"""Feedback service — enrichment over raw run rows.

Public callers (api/, cli/, mcp/) MUST import from this facade. The
submodules are private organisation.
"""

from __future__ import annotations

from agentbox.core.db.feedback.types import ActivityRange, since_iso
from agentbox.core.service.execution.feedback.analytics import (
    activity_summary,
    aggregate_usage,
    distinct_executors,
    enrich_recent_runs,
    success_rate,
    summary,
)
from agentbox.core.service.execution.feedback.comments import (
    add_comment,
    list_comments,
)

__all__ = [
    "activity_summary",
    "add_comment",
    "aggregate_usage",
    "distinct_executors",
    "enrich_recent_runs",
    "list_comments",
    "since_iso",
    "success_rate",
    "summary",
    "ActivityRange",
]

